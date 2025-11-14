"""Authentication endpoints."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..core.security import create_access_token, get_password_hash, verify_password
from ..models.models import Role, User
from ..schemas import auth as auth_schemas
from .deps import get_current_user, get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=auth_schemas.Token)
def register_user(payload: auth_schemas.RegisterRequest, db: Session = Depends(get_db_session)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        department_id=payload.department_id,
    )
    default_role = db.query(Role).filter(Role.name == "employee").first()
    if default_role:
        user.roles.append(default_role)
    db.add(user)
    db.commit()
    token = create_access_token(user.email)
    return auth_schemas.Token(access_token=token)


@router.post("/login", response_model=auth_schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect email or password")
    token = create_access_token(user.email, expires_delta=timedelta(minutes=60 * 24))
    return auth_schemas.Token(access_token=token)


@router.get("/me", response_model=auth_schemas.RegisterRequest)
def read_current_user(current_user: User = Depends(get_current_user)):
    return auth_schemas.RegisterRequest(
        email=current_user.email,
        full_name=current_user.full_name,
        password="***",
        department_id=current_user.department_id,
    )
