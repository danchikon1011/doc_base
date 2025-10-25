from __future__ import annotations

import enum
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


class Role(enum.Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(Role), default=Role.VIEWER, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    documents = db.relationship("Document", back_populates="owner", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

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


@login_manager.user_loader
def load_user(user_id: str) -> Optional["User"]:
    if user_id is None:
        return None
    return User.query.get(int(user_id))


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    slug = db.Column(db.String(255), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    current_version_id = db.Column(db.Integer, db.ForeignKey("document_version.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = db.relationship("User", back_populates="documents")
    current_version = db.relationship("DocumentVersion", foreign_keys=[current_version_id], post_update=True)
    versions = db.relationship(
        "DocumentVersion",
        back_populates="document",
        order_by="DocumentVersion.version_number.desc()",
        cascade="all, delete-orphan",
        foreign_keys="DocumentVersion.document_id",
    )

    def ensure_slug(self) -> None:
        base_slug = "-".join(self.title.lower().split())
        if not base_slug:
            base_slug = f"document-{self.id or ''}"
        slug = base_slug
        counter = 1
        while Document.query.filter_by(slug=slug).first() and slug != self.slug:
            counter += 1
            slug = f"{base_slug}-{counter}"
        self.slug = slug


class DocumentVersion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey("document.id"), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    filename = db.Column(db.String(255), nullable=True)
    file_path = db.Column(db.String(500), nullable=True)
    content = db.Column(db.Text, nullable=False)
    editor_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    comment = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    document = db.relationship(
        "Document",
        back_populates="versions",
        foreign_keys=[document_id],
    )
    editor = db.relationship("User")

    def storage_path(self) -> Optional[Path]:
        return Path(self.file_path) if self.file_path else None


class SearchIndex(db.Model):
    __tablename__ = "search_index"

    rowid = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)

    @staticmethod
    def rebuild_for_document(document: Document) -> None:
        SearchIndex.query.filter_by(document_id=document.id).delete()
        if not document.current_version:
            return
        index_entry = SearchIndex(document_id=document.id, content=document.current_version.content)
        db.session.add(index_entry)


def create_default_admin(username: str, password: str) -> User:
    user = User.query.filter_by(username=username).first()
    if user:
        return user
    user = User(username=username, role=Role.ADMIN)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user
