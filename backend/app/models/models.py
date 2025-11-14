"""ORM models for the document management system."""
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import relationship

from .base import Base


# Association table for many-to-many relation between users and roles
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

# Association table for access control when documents are shared with specific users
shared_document_users = Table(
    "shared_document_users",
    Base.metadata,
    Column("document_id", ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class DocumentStatus(str, Enum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"


class AccessLevel(str, Enum):
    owner_only = "owner"
    department = "department"
    custom_users = "custom"
    organization = "organization"


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

    users = relationship("User", secondary=user_roles, back_populates="roles")


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

    users = relationship("User", back_populates="department")
    documents = relationship("Document", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)

    department_id = Column(Integer, ForeignKey("departments.id"))

    department = relationship("Department", back_populates="users")
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    owned_documents = relationship("Document", back_populates="owner", foreign_keys="Document.owner_id")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(50), nullable=False)
    storage_path = Column(String(255), nullable=False)
    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.draft, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    access_level = Column(SQLEnum(AccessLevel), default=AccessLevel.owner_only)
    metadata_json = Column("metadata", JSON, default=dict)

    owner = relationship("User", back_populates="owned_documents", foreign_keys=[owner_id])
    department = relationship("Department", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    approvals = relationship("DocumentApproval", back_populates="document", cascade="all, delete-orphan")
    text_index = relationship(
        "DocumentTextIndex", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )
    access_rules = relationship("DocumentAccessRule", back_populates="document", cascade="all, delete-orphan")
    shared_users = relationship("User", secondary=shared_document_users)

    @property
    def metadata(self):
        return self.metadata_json or {}

    @metadata.setter
    def metadata(self, value):
        self.metadata_json = value or {}


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    comment = Column(String(255), nullable=True)
    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    metadata_snapshot = Column(JSON, default=dict)
    storage_path = Column(String(255), nullable=False)

    document = relationship("Document", back_populates="versions")
    changed_by = relationship("User")


class DocumentApproval(Base):
    __tablename__ = "document_approvals"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.draft)
    comment = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="approvals")
    user = relationship("User")


class DocumentAccessRule(Base):
    __tablename__ = "document_access_rules"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    can_view = Column(Boolean, default=True)
    can_edit = Column(Boolean, default=False)

    document = relationship("Document", back_populates="access_rules")
    user = relationship("User")
    department = relationship("Department")


class DocumentTextIndex(Base):
    __tablename__ = "document_text_index"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    raw_text = Column(Text, default="")
    summary = Column(Text, default="")

    document = relationship("Document", back_populates="text_index")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    action = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    details = Column(JSON, default=dict)

    user = relationship("User")
    document = relationship("Document")
