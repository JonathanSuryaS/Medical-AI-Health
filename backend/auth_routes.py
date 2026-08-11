"""
auth_routes.py -- the signup, login, and "who am I" endpoints.
 
FLOW:
  POST /auth/signup  -> create user (hashed pw), return a token
  POST /auth/login   -> check pw, return a token
  the get_current_user dependency -> reads the token on protected routes, gives
                                     back the User, or 401s
 
get_current_user is the reusable gate: any route that adds it as a dependency
becomes login-only, and receives the logged-in user automatically. That's how
/ask and /history become per-user in Phase 5 -- just add this dependency.
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
bearer = HTTPBearer(auto_error=False)   # reads the "Authorization: Bearer <token>" header


# ---- schemas ----
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    acess_token: str
    token_type: str = "bearer"
    email: str
    

# ---- the reusable "who is logged in" gate ----
def get_current_user(
    creds: HTTPAuthorizationCredentials | None  = Depends(bearer),
    db: Session = Depends(get_session),
) -> User:
    """Dependency that turns a token into a User, or raises 401. Add it to any
    route to make that route require login."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authorized")
    user_id = decode_token(creds.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exist")
    return user


# ---- routes ----
@router.post("/signup", response_model= TokenResponse)
def signup(req: SignupRequest, db: Session = Depends(get_session)) -> TokenResponse:
    if users_repo.get_user_by_email(db, req.email):
        # Don't reveal much -- but a duplicate email genuinely can't proceed.
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with that email exist")
    user = users_repo.create_user(db, req.email, req.password)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_session)) -> TokenResponse:
    user = users_repo.get_user_by_email(db, req.email)


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    """Quick check that a token is valid and see who it belongs to."""
    return {"id": user.id, "email": user.email}

