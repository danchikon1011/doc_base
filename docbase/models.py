from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .security import UserMixin


def _utcnow() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _to_iso(value: datetime | None) -> Optional[str]:
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat()


def _from_iso(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


class Role(enum.Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class ApprovalState(enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalDecision(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass
class User(UserMixin):
    id: int
    username: str
    password_hash: str
    role: Role
    created_at: datetime

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_editor(self) -> bool:
        return self.role in {Role.ADMIN, Role.EDITOR}

    @property
    def role_label(self) -> str:
        mapping = {
            Role.ADMIN: "Администратор",
            Role.EDITOR: "Редактор",
            Role.VIEWER: "Наблюдатель",
        }
        return mapping.get(self.role, self.role.value)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (self.password_hash, self.id),
        )

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @classmethod
    def from_row(cls, row) -> "User":
        return cls(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            role=Role(row["role"]),
            created_at=_from_iso(row["created_at"]) or _utcnow(),
        )

    @classmethod
    def get(cls, user_id: int | str | None) -> Optional["User"]:
        if user_id is None:
            return None
        row = db.query_one("SELECT * FROM users WHERE id = ?", (int(user_id),))
        if row is None:
            return None
        return cls.from_row(row)

    @classmethod
    def get_by_username(cls, username: str) -> Optional["User"]:
        row = db.query_one("SELECT * FROM users WHERE username = ?", (username,))
        if row is None:
            return None
        return cls.from_row(row)

    @classmethod
    def create(cls, username: str, password: str, role: Role) -> "User":
        now = _utcnow()
        password_hash = generate_password_hash(password)
        cursor = db.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, role.value, _to_iso(now)),
        )
        return cls(
            id=cursor.lastrowid,
            username=username,
            password_hash=password_hash,
            role=role,
            created_at=now,
        )

    @classmethod
    def list_editors(cls) -> List["User"]:
        rows = db.query(
            "SELECT * FROM users WHERE role IN (?, ?) ORDER BY username ASC",
            (Role.ADMIN.value, Role.EDITOR.value),
        )
        return [cls.from_row(row) for row in rows]


@dataclass
class DocumentVersion:
    id: int
    document_id: int
    version_number: int
    filename: Optional[str]
    file_path: Optional[str]
    file_extension: Optional[str]
    mime_type: Optional[str]
    file_size: Optional[int]
    content: str
    editor_id: Optional[int]
    comment: Optional[str]
    created_at: datetime

    editor: Optional[User] = None

    @property
    def is_editable(self) -> bool:
        if not self.file_extension:
            return True
        from .utils import EDITABLE_EXTENSIONS

        return self.file_extension.lower() in EDITABLE_EXTENSIONS

    @property
    def storage_path(self) -> Optional[Path]:
        return Path(self.file_path) if self.file_path else None

    @property
    def size_label(self) -> str:
        if not self.file_size:
            return "—"
        size = float(self.file_size)
        for unit in ["Б", "КБ", "МБ", "ГБ"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} ТБ"

    @classmethod
    def from_row(cls, row) -> "DocumentVersion":
        version = cls(
            id=row["id"],
            document_id=row["document_id"],
            version_number=row["version_number"],
            filename=row["filename"],
            file_path=row["file_path"],
            file_extension=row["file_extension"],
            mime_type=row["mime_type"],
            file_size=row["file_size"],
            content=row["content"],
            editor_id=row["editor_id"],
            comment=row["comment"],
            created_at=_from_iso(row["created_at"]) or _utcnow(),
        )
        if version.editor_id:
            version.editor = User.get(version.editor_id)
        return version

    @classmethod
    def get(cls, version_id: int | None) -> Optional["DocumentVersion"]:
        if version_id is None:
            return None
        row = db.query_one(
            "SELECT * FROM document_versions WHERE id = ?",
            (version_id,),
        )
        if row is None:
            return None
        return cls.from_row(row)

    @classmethod
    def list_for_document(cls, document_id: int) -> List["DocumentVersion"]:
        rows = db.query(
            "SELECT * FROM document_versions WHERE document_id = ? ORDER BY version_number DESC",
            (document_id,),
        )
        return [cls.from_row(row) for row in rows]

    @classmethod
    def create(
        cls,
        *,
        document_id: int,
        version_number: int,
        content: str,
        editor_id: Optional[int],
        comment: str,
        filename: Optional[str] = None,
        file_path: Optional[str] = None,
        file_extension: Optional[str] = None,
        mime_type: Optional[str] = None,
        file_size: Optional[int] = None,
    ) -> "DocumentVersion":
        now = _utcnow()
        cursor = db.execute(
            """
            INSERT INTO document_versions(
                document_id, version_number, filename, file_path, file_extension,
                mime_type, file_size, content, editor_id, comment, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                version_number,
                filename,
                file_path,
                file_extension,
                mime_type,
                file_size,
                content,
                editor_id,
                comment,
                _to_iso(now),
            ),
        )
        return cls.from_row(
            db.query_one("SELECT * FROM document_versions WHERE id = ?", (cursor.lastrowid,))
        )


@dataclass
class DocumentApproval:
    id: int
    document_id: int
    requested_by_id: int
    assigned_to_id: int
    status: ApprovalDecision
    comment: Optional[str]
    created_at: datetime
    decided_at: Optional[datetime]
    resolution_note: Optional[str]

    requested_by: Optional[User] = None
    assigned_to: Optional[User] = None

    @property
    def status_label(self) -> str:
        mapping = {
            ApprovalDecision.PENDING: "В ожидании",
            ApprovalDecision.APPROVED: "Согласовано",
            ApprovalDecision.REJECTED: "Отклонено",
            ApprovalDecision.CANCELLED: "Отменено",
        }
        return mapping.get(self.status, self.status.value)

    @classmethod
    def from_row(cls, row) -> "DocumentApproval":
        approval = cls(
            id=row["id"],
            document_id=row["document_id"],
            requested_by_id=row["requested_by_id"],
            assigned_to_id=row["assigned_to_id"],
            status=ApprovalDecision(row["status"]),
            comment=row["comment"],
            created_at=_from_iso(row["created_at"]) or _utcnow(),
            decided_at=_from_iso(row["decided_at"]),
            resolution_note=row["resolution_note"],
        )
        approval.requested_by = User.get(approval.requested_by_id)
        approval.assigned_to = User.get(approval.assigned_to_id)
        return approval

    @classmethod
    def list_for_document(cls, document_id: int) -> List["DocumentApproval"]:
        rows = db.query(
            "SELECT * FROM document_approvals WHERE document_id = ? ORDER BY created_at DESC",
            (document_id,),
        )
        return [cls.from_row(row) for row in rows]

    @classmethod
    def get(cls, approval_id: int | str | None) -> Optional["DocumentApproval"]:
        if approval_id is None:
            return None
        row = db.query_one(
            "SELECT * FROM document_approvals WHERE id = ?",
            (int(approval_id),),
        )
        if row is None:
            return None
        return cls.from_row(row)

    @classmethod
    def create(
        cls,
        *,
        document_id: int,
        requested_by: User,
        assigned_to: User,
        comment: Optional[str],
    ) -> "DocumentApproval":
        now = _utcnow()
        cursor = db.execute(
            """
            INSERT INTO document_approvals(
                document_id, requested_by_id, assigned_to_id, status, comment,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                requested_by.id,
                assigned_to.id,
                ApprovalDecision.PENDING.value,
                comment,
                _to_iso(now),
            ),
        )
        return cls.get(cursor.lastrowid)

    def approve(self, note: Optional[str] = None) -> None:
        now = _utcnow()
        db.execute(
            "UPDATE document_approvals SET status = ?, decided_at = ?, resolution_note = ? WHERE id = ?",
            (ApprovalDecision.APPROVED.value, _to_iso(now), note, self.id),
        )
        self.status = ApprovalDecision.APPROVED
        self.decided_at = now
        self.resolution_note = note

    def reject(self, note: Optional[str] = None) -> None:
        now = _utcnow()
        db.execute(
            "UPDATE document_approvals SET status = ?, decided_at = ?, resolution_note = ? WHERE id = ?",
            (ApprovalDecision.REJECTED.value, _to_iso(now), note, self.id),
        )
        self.status = ApprovalDecision.REJECTED
        self.decided_at = now
        self.resolution_note = note

    def cancel(self, reason: Optional[str] = None) -> None:
        if self.status is not ApprovalDecision.PENDING:
            return
        now = _utcnow()
        db.execute(
            "UPDATE document_approvals SET status = ?, decided_at = ?, resolution_note = ? WHERE id = ?",
            (ApprovalDecision.CANCELLED.value, _to_iso(now), reason, self.id),
        )
        self.status = ApprovalDecision.CANCELLED
        self.decided_at = now
        self.resolution_note = reason

    @staticmethod
    def cancel_pending_for_document(document_id: int, reason: str) -> None:
        rows = db.query(
            "SELECT id FROM document_approvals WHERE document_id = ? AND status = ?",
            (document_id, ApprovalDecision.PENDING.value),
        )
        for row in rows:
            approval = DocumentApproval.get(row["id"])
            if approval:
                approval.cancel(reason)


@dataclass
class Document:
    id: int
    title: str
    summary: Optional[str]
    slug: str
    owner_id: int
    current_version_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    approval_state: ApprovalState

    owner: Optional[User] = None
    current_version: Optional[DocumentVersion] = None
    versions: List[DocumentVersion] = field(default_factory=list)
    approvals: List[DocumentApproval] = field(default_factory=list)

    def attach_related(self) -> "Document":
        self.owner = User.get(self.owner_id)
        self.current_version = DocumentVersion.get(self.current_version_id)
        self.versions = DocumentVersion.list_for_document(self.id)
        self.approvals = DocumentApproval.list_for_document(self.id)
        return self

    @property
    def approval_label(self) -> str:
        mapping = {
            ApprovalState.DRAFT: "Черновик",
            ApprovalState.PENDING: "На согласовании",
            ApprovalState.APPROVED: "Согласован",
            ApprovalState.REJECTED: "Отклонен",
        }
        return mapping.get(self.approval_state, self.approval_state.value)

    @classmethod
    def from_row(cls, row) -> "Document":
        created_at = _from_iso(row["created_at"]) or _utcnow()
        updated_at = _from_iso(row["updated_at"]) or created_at
        return cls(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            slug=row["slug"],
            owner_id=row["owner_id"],
            current_version_id=row["current_version_id"],
            created_at=created_at,
            updated_at=updated_at,
            approval_state=ApprovalState(row["approval_state"]),
        )

    @classmethod
    def get(cls, document_id: int) -> Optional["Document"]:
        row = db.query_one("SELECT * FROM documents WHERE id = ?", (document_id,))
        if row is None:
            return None
        return cls.from_row(row)

    @classmethod
    def get_by_slug(cls, slug: str) -> Optional["Document"]:
        row = db.query_one("SELECT * FROM documents WHERE slug = ?", (slug,))
        if row is None:
            return None
        return cls.from_row(row)

    @classmethod
    def list_all(cls) -> List["Document"]:
        rows = db.query(
            "SELECT * FROM documents ORDER BY updated_at DESC, created_at DESC"
        )
        documents = [cls.from_row(row) for row in rows]
        for document in documents:
            document.owner = User.get(document.owner_id)
            document.current_version = DocumentVersion.get(document.current_version_id)
        return documents

    @staticmethod
    def _generate_slug(title: str, existing_id: Optional[int] = None) -> str:
        base_slug = "-".join(title.lower().split()) or "document"
        slug = base_slug
        counter = 1
        while True:
            row = db.query_one("SELECT id FROM documents WHERE slug = ?", (slug,))
            if row is None or (existing_id is not None and row["id"] == existing_id):
                return slug
            counter += 1
            slug = f"{base_slug}-{counter}"

    @classmethod
    def create(
        cls,
        *,
        title: str,
        summary: Optional[str],
        owner: User,
        content: str,
        version_comment: str,
        filename: Optional[str] = None,
        file_path: Optional[str] = None,
        file_extension: Optional[str] = None,
        mime_type: Optional[str] = None,
        file_size: Optional[int] = None,
    ) -> "Document":
        slug = cls._generate_slug(title)
        now = _utcnow()
        document_id: Optional[int] = None
        with db.transaction():
            cursor = db.execute(
                """
                INSERT INTO documents(
                    title, summary, slug, owner_id, current_version_id,
                    created_at, updated_at, approval_state
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    title,
                    summary,
                    slug,
                    owner.id,
                    _to_iso(now),
                    _to_iso(now),
                    ApprovalState.DRAFT.value,
                ),
            )
            document_id = cursor.lastrowid
            version = DocumentVersion.create(
                document_id=document_id,
                version_number=1,
                content=content,
                editor_id=owner.id,
                comment=version_comment,
                filename=filename,
                file_path=file_path,
                file_extension=file_extension,
                mime_type=mime_type,
                file_size=file_size,
            )
            db.execute(
                "UPDATE documents SET current_version_id = ? WHERE id = ?",
                (version.id, document_id),
            )
            SearchIndex.rebuild_for_document_id(document_id)
        if document_id is None:
            raise RuntimeError("Не удалось создать документ")
        document = cls.get(document_id)
        if document is None:
            raise RuntimeError("Не удалось создать документ")
        return document.attach_related()

    def update_summary(self, summary: Optional[str]) -> None:
        now = _utcnow()
        db.execute(
            "UPDATE documents SET summary = ?, updated_at = ? WHERE id = ?",
            (summary, _to_iso(now), self.id),
        )
        self.summary = summary
        self.updated_at = now

    def set_current_version(self, version: DocumentVersion) -> None:
        now = _utcnow()
        db.execute(
            "UPDATE documents SET current_version_id = ?, updated_at = ? WHERE id = ?",
            (version.id, _to_iso(now), self.id),
        )
        self.current_version = version
        self.current_version_id = version.id
        self.updated_at = now

    def reset_approvals(self) -> None:
        DocumentApproval.cancel_pending_for_document(
            self.id, "Создана новая версия документа"
        )
        db.execute(
            "UPDATE documents SET approval_state = ? WHERE id = ?",
            (ApprovalState.DRAFT.value, self.id),
        )
        self.approval_state = ApprovalState.DRAFT
        self.approvals = DocumentApproval.list_for_document(self.id)

    def set_approval_state(self, state: ApprovalState) -> None:
        db.execute(
            "UPDATE documents SET approval_state = ?, updated_at = ? WHERE id = ?",
            (state.value, _to_iso(_utcnow()), self.id),
        )
        self.approval_state = state

    def add_version(
        self,
        *,
        editor: User,
        content: str,
        comment: str,
        summary: Optional[str],
        filename: Optional[str] = None,
        file_path: Optional[str] = None,
        file_extension: Optional[str] = None,
        mime_type: Optional[str] = None,
        file_size: Optional[int] = None,
    ) -> DocumentVersion:
        previous = self.current_version or DocumentVersion.get(self.current_version_id)
        version_number = (previous.version_number if previous else 0) + 1
        version = DocumentVersion.create(
            document_id=self.id,
            version_number=version_number,
            content=content,
            editor_id=editor.id,
            comment=comment,
            filename=filename if filename is not None else (previous.filename if previous else None),
            file_path=file_path if file_path is not None else (previous.file_path if previous else None),
            file_extension=file_extension if file_extension is not None else (previous.file_extension if previous else None),
            mime_type=mime_type if mime_type is not None else (previous.mime_type if previous else None),
            file_size=file_size if file_size is not None else (previous.file_size if previous else None),
        )
        now = _utcnow()
        DocumentApproval.cancel_pending_for_document(
            self.id, "Создана новая версия документа"
        )
        db.execute(
            """
            UPDATE documents
            SET summary = ?, current_version_id = ?, updated_at = ?, approval_state = ?
            WHERE id = ?
            """,
            (
                summary,
                version.id,
                _to_iso(now),
                ApprovalState.DRAFT.value,
                self.id,
            ),
        )
        self.summary = summary
        self.current_version = version
        self.current_version_id = version.id
        self.updated_at = now
        self.approval_state = ApprovalState.DRAFT
        SearchIndex.rebuild_for_document_id(self.id)
        self.approvals = DocumentApproval.list_for_document(self.id)
        return version


@dataclass
class SearchIndexEntry:
    id: int
    document_id: int
    content: str

    @classmethod
    def all(cls) -> List["SearchIndexEntry"]:
        rows = db.query("SELECT * FROM search_index")
        return [cls(id=row["id"], document_id=row["document_id"], content=row["content"]) for row in rows]


class SearchIndex:
    @staticmethod
    def rebuild_for_document(document: Document) -> None:
        SearchIndex.rebuild_for_document_id(document.id)

    @staticmethod
    def rebuild_for_document_id(document_id: int) -> None:
        db.execute("DELETE FROM search_index WHERE document_id = ?", (document_id,))
        document = Document.get(document_id)
        if not document or not document.current_version_id:
            return
        version = DocumentVersion.get(document.current_version_id)
        if not version:
            return
        db.execute(
            "INSERT INTO search_index(document_id, content) VALUES (?, ?)",
            (document_id, version.content),
        )

    @staticmethod
    def all() -> List[SearchIndexEntry]:
        return SearchIndexEntry.all()


def load_user(user_id: str | None) -> Optional[User]:
    return User.get(user_id)


def create_default_admin(username: str, password: str) -> User:
    existing = User.get_by_username(username)
    if existing:
        return existing
    return User.create(username=username, password=password, role=Role.ADMIN)
