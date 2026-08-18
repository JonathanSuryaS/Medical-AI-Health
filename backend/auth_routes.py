"""
auth_routes.py -- signup, login, and "who am I".

signup now relies on create_user's own duplicate handling (IntegrityError ->
ValueError) as the authoritative check. The pre-check is a fast path; the DB
unique constraint is the real guarantee. Either way the session gets rolled back
cleanly, so a duplicate signup returns 409 without poisoning later requests.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.models import User
from backend import users_repo
from backend.security import create_token, decode_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_session),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    user_id = decode_token(creds.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user no longer exists")
    return user


@router.post("/signup", response_model=TokenResponse)
def signup(req: SignupRequest, db: Session = Depends(get_session)) -> TokenResponse:
    try:
        user = users_repo.create_user(db, req.email, req.password)
    except ValueError:
        # duplicate email -- session already rolled back inside create_user
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with that email exists")
    return TokenResponse(access_token=create_token(user.id), email=user.email)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_session)) -> TokenResponse:
    user = users_repo.get_user_by_email(db, req.email)
    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect email or password")
    return TokenResponse(access_token=create_token(user.id), email=user.email)


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {"id": user.id, "email": user.email}