"""
users_repo.py -- the only file that reads/writes the users table.
 
Same repository pattern as history_repo.py: storage logic lives here, isolated
from the API. Two operations -- create a user, find a user by email -- which is
all signup and login need.
"""
 
from __future__ import annotations
 
from sqlalchemy import select
from sqlalchemy.orm import Session
 
from backend.models import User
from backend.security import hash_password
 
 
def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))
 
 
def create_user(db: Session, email: str, password: str) -> User:
    """Create a user with a HASHED password. The raw password is hashed here and
    never stored -- by the time anything hits the database, it's already a hash."""
    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user