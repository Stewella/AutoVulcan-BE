from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from db import get_db
from crud import get_user_by_username, get_user_by_email, create_user
from auth.jwt import hash_password, verify_password, create_access_token, get_current_user
from schemas import UserPublic, Token
from typing import Optional

router = APIRouter(prefix="/auth", tags=["Auth"]) 

@router.post("/register", response_model=Token, summary="Register user (returns JWT)")
def register_user(
    full_name: str = Form(..., description="Full name"),
    email: str = Form(..., description="Email"),
    password: str = Form(..., description="Password"),
    confirm_password: str = Form(..., description="Confirm Password"),
    db: Session = Depends(get_db),
):
    # basic validation
    if password != confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")

    # ensure email uniqueness
    if get_user_by_email(db, email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # derive a username from the email local-part, ensure uniqueness
    base_username = email.split("@")[0].lower()
    candidate = base_username
    suffix = 1
    while get_user_by_username(db, candidate):
        candidate = f"{base_username}{suffix}"
        suffix += 1

    hashed = hash_password(password)
    user = create_user(db, username=candidate, email=email, hashed_password=hashed, full_name=full_name)
    access_token = create_access_token(subject=user.username)
    return Token(access_token=access_token, token_type="bearer")

@router.post("/token", response_model=Token, summary="Login user with email (return JWT)")
def login_for_access_token(
    email: Optional[str] = Form(None, description="Email"),
    username: Optional[str] = Form(None, description="Username (treated as email for OAuth2 UI)"),
    password: str = Form(..., description="Password"),
    db: Session = Depends(get_db),
):
    # Support both 'email' and OAuth2PasswordRequestForm's 'username' (treated as email)
    login_email = email or username
    if not login_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")

    user = get_user_by_email(db, login_email)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    access_token = create_access_token(subject=user.username)
    return Token(access_token=access_token, token_type="bearer")

@router.get("/me", response_model=UserPublic, summary="Get current user")
def read_users_me(current_user: dict = Depends(get_current_user)):
    return UserPublic(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user["email"],
        full_name=current_user.get("full_name"),
        is_active=current_user["is_active"],
        created_at=current_user["created_at"],
    )