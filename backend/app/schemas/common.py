"""Pydantic schemas shared across endpoints."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from ..models.models import AccessLevel, DocumentStatus


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None


class Role(RoleBase):
    id: int

    class Config:
        orm_mode = True


class DepartmentBase(BaseModel):
    name: str
    description: Optional[str] = None


class Department(DepartmentBase):
    id: int

    class Config:
        orm_mode = True


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    is_active: bool = True
    department_id: Optional[int] = None
    role_ids: List[int] = Field(default_factory=list)


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    department_id: Optional[int] = None
    role_ids: Optional[List[int]] = None


class User(UserBase):
    id: int
    roles: List[Role] = []

    class Config:
        orm_mode = True


class DocumentMetadata(BaseModel):
    title: str
    status: DocumentStatus
    owner_id: int
    department_id: Optional[int]
    access_level: AccessLevel
    metadata: dict


class DocumentBase(BaseModel):
    title: str
    department_id: Optional[int]
    access_level: AccessLevel = AccessLevel.owner_only
    shared_user_ids: List[int] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    department_id: Optional[int] = None
    access_level: Optional[AccessLevel] = None
    shared_user_ids: Optional[List[int]] = None
    metadata: Optional[dict] = None
    status: Optional[DocumentStatus] = None
    comment: Optional[str] = None


class Document(DocumentBase):
    id: int
    status: DocumentStatus
    owner_id: int
    filename: str
    content_type: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class DocumentVersion(BaseModel):
    id: int
    version_number: int
    comment: Optional[str]
    changed_by_id: int
    created_at: datetime
    metadata_snapshot: dict

    class Config:
        orm_mode = True


class DocumentApproval(BaseModel):
    id: int
    user_id: int
    status: DocumentStatus
    comment: Optional[str]
    updated_at: datetime

    class Config:
        orm_mode = True


class DocumentSearchResult(BaseModel):
    document: Document
    snippet: str
    score: float


class SmartSearchResponse(BaseModel):
    answer: str
    results: List[DocumentSearchResult]
