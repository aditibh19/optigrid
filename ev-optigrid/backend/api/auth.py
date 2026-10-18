"""Auth endpoints (spec §26/§34)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field

from api.deps import get_current_user, user_from_token
from database.session import get_db
from models.user import User
from services.auth_service import hash_password, verify_password, create_access_token, create_refresh_token

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(email=payload.email, password_hash=hash_password(payload.password), name=payload.name)
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(access_token=create_access_token(user.id), refresh_token=create_refresh_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    return TokenResponse(access_token=create_access_token(user.id), refresh_token=create_refresh_token(user.id))


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    """Exchanges a valid refresh token for a new access + refresh pair."""
    user = user_from_token(payload.refresh_token, "refresh", db)
    return TokenResponse(access_token=create_access_token(user.id), refresh_token=create_refresh_token(user.id))


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email, name=user.name)
