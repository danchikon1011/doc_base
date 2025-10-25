from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from flask import current_app, g

import sqlite3


def _get_database_path() -> Path:
    database_setting = current_app.config.get("DATABASE_PATH")
    if database_setting:
        return Path(database_setting)
    # Backwards compatibility with older configuration values.
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "sqlite:///docbase.db")
    if uri.startswith("sqlite:///"):
        return Path(uri.replace("sqlite:///", ""))
    raise RuntimeError(
        "DocBase now requires DATABASE_PATH configuration when not using SQLite URI."
    )


def _ensure_connection() -> sqlite3.Connection:
    if "_docbase_conn" not in g:
        db_path = _get_database_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g._docbase_conn = connection
    return g._docbase_conn  # type: ignore[attr-defined]


def _close_connection(_: Optional[BaseException]) -> None:
    connection: Optional[sqlite3.Connection] = g.pop("_docbase_conn", None)
    if connection is not None:
        connection.commit()
        connection.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    summary TEXT,
    slug TEXT NOT NULL UNIQUE,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    current_version_id INTEGER REFERENCES document_versions(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    approval_state TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    filename TEXT,
    file_path TEXT,
    file_extension TEXT,
    mime_type TEXT,
    file_size INTEGER,
    content TEXT NOT NULL,
    editor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    comment TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    requested_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_to_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    resolution_note TEXT
);

CREATE TABLE IF NOT EXISTS search_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_documents_updated_at
    ON documents(updated_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_documents_slug ON documents(slug);
CREATE INDEX IF NOT EXISTS ix_document_versions_document_id
    ON document_versions(document_id, version_number DESC);
CREATE INDEX IF NOT EXISTS ix_document_approvals_document_id
    ON document_approvals(document_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_search_index_document_id
    ON search_index(document_id);
"""


@dataclass
class SimpleDatabase:
    """A lightweight helper that mimics the small subset of the old db helper."""

    def init_app(self, app) -> None:
        app.teardown_appcontext(_close_connection)

    def create_all(self) -> None:
        connection = _ensure_connection()
        connection.executescript(SCHEMA)
        connection.commit()

    # Convenience helpers --------------------------------------------------
    def connection(self) -> sqlite3.Connection:
        return _ensure_connection()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = self.connection()
        cursor = conn.execute(sql, params)
        if not conn.in_transaction:
            conn.commit()
        return cursor

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        cursor = self.connection().execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()
        return rows

    def query_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        cursor = self.connection().execute(sql, params)
        row = cursor.fetchone()
        cursor.close()
        return row

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connection()
        try:
            connection.execute("BEGIN")
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()


db = SimpleDatabase()

