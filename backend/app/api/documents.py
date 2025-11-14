"""Document management endpoints."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..models.models import (
    AccessLevel,
    AuditLog,
    Document,
    DocumentApproval,
    DocumentStatus,
    DocumentTextIndex,
    DocumentVersion,
    User,
)
from ..schemas.common import Document as DocumentSchema
from ..schemas.common import DocumentApproval as DocumentApprovalSchema
from ..schemas.common import DocumentVersion as DocumentVersionSchema
from ..schemas.common import DocumentUpdate
from ..services import access as access_service
from ..services.search import build_smart_answer, simple_keyword_search
from ..utils.file_processing import SUPPORTED_EXTENSIONS, build_storage_path, extract_text_from_file, save_upload_file
from .deps import get_current_user, get_db_session

router = APIRouter(prefix="/documents", tags=["documents"])


# Helpers --------------------------------------------------------------------

def _parse_json_list(raw: Optional[str]) -> list[int]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [int(v) for v in value]
    except Exception:
        pass
    return []


def _log_action(db: Session, action: str, user: User, document: Document, details: Optional[dict] = None):
    db.add(
        AuditLog(
            action=action,
            user_id=user.id if user else None,
            document_id=document.id if document else None,
            details=details or {},
        )
    )


def _create_version(db: Session, document: Document, user: User, storage_path: Path, comment: str | None = None):
    version_number = len(document.versions) + 1
    version = DocumentVersion(
        document_id=document.id,
        version_number=version_number,
        comment=comment,
        changed_by_id=user.id,
        created_at=datetime.utcnow(),
        metadata_snapshot={
            "title": document.title,
            "metadata": document.metadata,
            "status": document.status.value,
        },
        storage_path=str(storage_path),
    )
    db.add(version)
    return version


def _update_text_index(db: Session, document: Document, raw_text: str):
    if document.text_index:
        document.text_index.raw_text = raw_text
        document.text_index.summary = raw_text[:500]
    else:
        db.add(
            DocumentTextIndex(
                document=document,
                raw_text=raw_text,
                summary=raw_text[:500],
            )
        )


# Routes ---------------------------------------------------------------------


@router.post("/upload", response_model=DocumentSchema)
def upload_document(
    title: str = Form(...),
    department_id: Optional[str] = Form(None),
    access_level: AccessLevel = Form(AccessLevel.owner_only),
    shared_user_ids: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    reviewers: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    filename = f"{uuid.uuid4()}{suffix}"
    storage_path = build_storage_path(filename)
    save_upload_file(file, storage_path)
    raw_text = extract_text_from_file(storage_path)

    department_id_value = int(department_id) if department_id else None

    document = Document(
        title=title,
        filename=file.filename,
        content_type=file.content_type,
        storage_path=str(storage_path),
        owner_id=current_user.id,
        department_id=department_id_value,
        access_level=access_level,
        metadata={},
    )
    if metadata:
        try:
            document.metadata = json.loads(metadata)
        except json.JSONDecodeError:
            document.metadata = {"notes": metadata}

    db.add(document)
    db.flush()  # assign id

    shared_ids = _parse_json_list(shared_user_ids)
    if shared_ids:
        users = db.query(User).filter(User.id.in_(shared_ids)).all()
        document.shared_users = users

    _create_version(db, document, current_user, storage_path, comment="Initial upload")
    _update_text_index(db, document, raw_text)

    reviewer_ids = _parse_json_list(reviewers)
    for reviewer_id in reviewer_ids:
        db.add(
            DocumentApproval(
                document_id=document.id,
                user_id=reviewer_id,
                status=DocumentStatus.in_review,
            )
        )

    document.status = DocumentStatus.draft

    _log_action(db, "create_document", current_user, document, {"filename": file.filename})

    db.commit()
    db.refresh(document)
    return document


@router.get("/", response_model=list[DocumentSchema])
def list_documents(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    status_filter: Optional[DocumentStatus] = None,
    q: Optional[str] = None,
):
    query = db.query(Document)
    if status_filter:
        query = query.filter(Document.status == status_filter)
    if q:
        query = query.filter(Document.title.ilike(f"%{q}%"))
    documents = query.order_by(Document.updated_at.desc()).all()
    visible = access_service.filter_documents_for_user(current_user, documents)
    return visible


@router.get("/{document_id}")
def document_detail(
    document_id: int,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if not access_service.can_view_document(current_user, document):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "document": DocumentSchema.from_orm(document),
        "versions": [DocumentVersionSchema.from_orm(v) for v in document.versions],
        "approvals": [DocumentApprovalSchema.from_orm(a) for a in document.approvals],
        "text": document.text_index.raw_text if document.text_index else "",
    }


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document or not access_service.can_view_document(current_user, document):
        raise HTTPException(status_code=404, detail="Document not accessible")
    return FileResponse(document.storage_path, filename=document.filename, media_type=document.content_type)


@router.put("/{document_id}", response_model=DocumentSchema)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.owner_id != current_user.id and not access_service.user_has_role(current_user, "admin"):
        raise HTTPException(status_code=403, detail="Only owner or admin can update")

    changed = False
    if payload.title is not None:
        document.title = payload.title
        changed = True
    if payload.department_id is not None:
        document.department_id = payload.department_id
        changed = True
    if payload.metadata is not None:
        document.metadata = payload.metadata
        changed = True
    if payload.access_level is not None:
        document.access_level = payload.access_level
        changed = True
    if payload.shared_user_ids is not None:
        users = db.query(User).filter(User.id.in_(payload.shared_user_ids)).all()
        document.shared_users = users
        changed = True
    if payload.status and payload.status != document.status:
        document.status = payload.status
        changed = True
        db.add(
            DocumentApproval(
                document_id=document.id,
                user_id=current_user.id,
                status=payload.status,
                comment=payload.comment,
            )
        )

    if changed:
        _create_version(
            db,
            document,
            current_user,
            Path(document.storage_path),
            comment=payload.comment or "Metadata updated",
        )
        _log_action(db, "update_document", current_user, document, {"fields": payload.dict(exclude_unset=True)})

    db.commit()
    db.refresh(document)
    return document


@router.post("/{document_id}/upload-version", response_model=DocumentSchema)
def upload_new_version(
    document_id: int,
    comment: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.owner_id != current_user.id and not access_service.user_has_role(current_user, "manager"):
        raise HTTPException(status_code=403, detail="Only owner or managers can upload new version")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    filename = f"{uuid.uuid4()}{suffix}"
    storage_path = build_storage_path(filename)
    save_upload_file(file, storage_path)
    raw_text = extract_text_from_file(storage_path)

    document.filename = file.filename
    document.content_type = file.content_type
    document.storage_path = str(storage_path)
    document.updated_at = datetime.utcnow()

    _create_version(db, document, current_user, storage_path, comment=comment or "New file uploaded")
    _update_text_index(db, document, raw_text)

    _log_action(db, "upload_new_version", current_user, document, {"filename": file.filename})

    db.commit()
    db.refresh(document)
    return document


@router.post("/{document_id}/review/{action}")
def review_document(
    document_id: int,
    action: str,
    comment: Optional[str] = Form(None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    approval = (
        db.query(DocumentApproval)
        .filter(DocumentApproval.document_id == document.id, DocumentApproval.user_id == current_user.id)
        .first()
    )
    if not approval:
        raise HTTPException(status_code=403, detail="You are not a reviewer")

    if action == "approve":
        document.status = DocumentStatus.approved
        approval.status = DocumentStatus.approved
    elif action == "reject":
        document.status = DocumentStatus.rejected
        approval.status = DocumentStatus.rejected
    else:
        raise HTTPException(status_code=400, detail="Unknown action")

    approval.comment = comment
    approval.updated_at = datetime.utcnow()

    _create_version(db, document, current_user, Path(document.storage_path), comment=comment or action)
    _log_action(db, f"review_{action}", current_user, document, {"comment": comment})

    db.commit()
    return {"status": document.status.value}


@router.get("/search")
def search_documents(
    q: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    results = simple_keyword_search(db, q)
    visible_results = [r for r in results if access_service.can_view_document(current_user, r.document)]
    return [
        {
            "document": DocumentSchema.from_orm(r.document),
            "snippet": r.snippet,
            "score": r.score,
        }
        for r in visible_results
    ]


@router.get("/smart-search")
def smart_search(
    question: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    results = simple_keyword_search(db, question, limit=5)
    visible_results = [r for r in results if access_service.can_view_document(current_user, r.document)]
    answer = build_smart_answer(visible_results, question)
    return {
        "answer": answer,
        "results": [
            {
                "document": DocumentSchema.from_orm(r.document),
                "snippet": r.snippet,
                "score": r.score,
            }
            for r in visible_results
        ],
    }
