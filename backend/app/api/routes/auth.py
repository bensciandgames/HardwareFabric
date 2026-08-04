"""
app/api/routes/auth.py

Minimal email/password auth issuing a JWT. This is the auth system referenced
throughout the schema/backend as "not yet chosen" — kept deliberately small
(no refresh tokens, no OAuth) so it's easy to replace later without touching
how downstream routes consume `get_current_user`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.auth import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db import create_user, fetch_user_by_email, fetch_user_by_id

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_PASSWORD_MIN_LEN = 8


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=_PASSWORD_MIN_LEN)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> TokenResponse:
    existing = await fetch_user_by_email(payload.email.lower())
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    user = await create_user(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
    )
    token = create_access_token(user_id=str(user["id"]), email=user["email"])
    return TokenResponse(
        access_token=token,
        user=UserResponse(id=str(user["id"]), email=user["email"], full_name=user["full_name"]),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    user = await fetch_user_by_email(payload.email.lower())
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(user_id=str(user["id"]), email=user["email"])
    return TokenResponse(
        access_token=token,
        user=UserResponse(id=str(user["id"]), email=user["email"], full_name=user["full_name"]),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> UserResponse:
    user = await fetch_user_by_id(current_user.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(id=str(user["id"]), email=user["email"], full_name=user["full_name"])
