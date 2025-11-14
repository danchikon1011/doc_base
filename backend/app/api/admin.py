"""Admin endpoints for managing users, departments and roles."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.security import get_password_hash
from ..models.models import AuditLog, Department, Role, User
from ..schemas.common import Department as DepartmentSchema
from ..schemas.common import Role as RoleSchema
from ..schemas.common import User as UserSchema
from ..schemas.common import UserCreate, UserUpdate
from .deps import get_admin_user, get_db_session

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_admin_user)])


@router.get("/users", response_model=list[UserSchema])
def list_users(db: Session = Depends(get_db_session)):
    return db.query(User).all()


@router.post("/users", response_model=UserSchema)
def create_user(payload: UserCreate, db: Session = Depends(get_db_session)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="User already exists")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        department_id=payload.department_id,
        is_active=payload.is_active,
    )
    if payload.role_ids:
        roles = db.query(Role).filter(Role.id.in_(payload.role_ids)).all()
        user.roles = roles
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserSchema)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.full_name:
        user.full_name = payload.full_name
    if payload.password:
        user.hashed_password = get_password_hash(payload.password)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.department_id is not None:
        user.department_id = payload.department_id
    if payload.role_ids is not None:
        roles = db.query(Role).filter(Role.id.in_(payload.role_ids)).all()
        user.roles = roles
    db.commit()
    db.refresh(user)
    return user


@router.get("/departments", response_model=list[DepartmentSchema])
def list_departments(db: Session = Depends(get_db_session)):
    return db.query(Department).all()


@router.post("/departments", response_model=DepartmentSchema)
def create_department(payload: DepartmentSchema, db: Session = Depends(get_db_session)):
    dept = Department(name=payload.name, description=payload.description)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


@router.get("/roles", response_model=list[RoleSchema])
def list_roles(db: Session = Depends(get_db_session)):
    return db.query(Role).all()


@router.post("/roles", response_model=RoleSchema)
def create_role(payload: RoleSchema, db: Session = Depends(get_db_session)):
    role = Role(name=payload.name, description=payload.description)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.get("/audit-logs")
def audit_logs(db: Session = Depends(get_db_session)):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return [
        {
            "id": log.id,
            "action": log.action,
            "user_id": log.user_id,
            "document_id": log.document_id,
            "created_at": log.created_at,
            "details": log.details,
        }
        for log in logs
    ]
