"""Centralized access-control helpers."""
from typing import Iterable

from sqlalchemy.orm import Session

from ..models.models import AccessLevel, Document, DocumentAccessRule, User


def user_has_role(user: User, role_name: str) -> bool:
    return any(role.name == role_name for role in user.roles)


def can_view_document(user: User, document: Document) -> bool:
    if document.owner_id == user.id:
        return True
    if document.access_level == AccessLevel.organization:
        return True
    if document.access_level == AccessLevel.department and user.department_id == document.department_id:
        return True
    if document.access_level == AccessLevel.custom_users and user in document.shared_users:
        return True
    # Additional fine-grained rules
    for rule in document.access_rules:
        if rule.user_id == user.id and rule.can_view:
            return True
        if rule.department_id == user.department_id and rule.can_view:
            return True
    return False


def filter_documents_for_user(user: User, documents: Iterable[Document]):
    return [document for document in documents if can_view_document(user, document)]


def ensure_can_view(db: Session, user: User, document: Document) -> Document:
    if not can_view_document(user, document):
        raise PermissionError("Недостаточно прав для просмотра документа")
    return document
