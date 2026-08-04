"""
app/api/routes/auth.py

Minimal email/password auth issuing a JWT. This is the auth system referenced
throughout the schema/backend as "not yet chosen" — kept deliberately small
(no refresh tokens, no OAuth) so it's easy to replace later without touching
how downstream routes consume `get_current_user`.
"""

from __future__ import annotations

import datetime as dt
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.auth import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.db import (
    create_user,
    fetch_user_by_email,
    fetch_user_by_id,
    set_verification_token,
    verify_user_by_token,
)
from app.services.email import send_verification_email

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
settings = get_settings()

_PASSWORD_MIN_LEN = 8


def _new_verification_token() -> tuple[str, dt.datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        hours=settings.email_verification_token_expire_hours
    )
    return token, expires_at


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=_PASSWORD_MIN_LEN)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    email_verified: bool = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class RegisterResponse(BaseModel):
    message: str
    email: str


class MessageResponse(BaseModel):
    message: str


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> RegisterResponse:
    existing = await fetch_user_by_email(payload.email.lower())
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    token, expires_at = _new_verification_token()
    user = await create_user(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        verification_token=token,
        verification_token_expires_at=expires_at,
    )
    await send_verification_email(user["email"], token)
    return RegisterResponse(
        message="Account created. Check your email for a verification link before logging in.",
        email=user["email"],
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    user = await fetch_user_by_email(payload.email.lower())
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user["email_verified"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in. Check your inbox, or request a new link.",
        )

    token = create_access_token(user_id=str(user["id"]), email=user["email"])
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=str(user["id"]), email=user["email"], full_name=user["full_name"],
            email_verified=user["email_verified"],
        ),
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(payload: VerifyEmailRequest) -> MessageResponse:
    user = await verify_user_by_token(payload.token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired. Request a new one.",
        )
    return MessageResponse(message="Email verified — you can log in now.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(payload: ResendVerificationRequest) -> MessageResponse:
    # Always returns the same generic message regardless of whether the
    # account exists or is already verified, so this endpoint can't be used
    # to enumerate registered emails.
    user = await fetch_user_by_email(payload.email.lower())
    if user is not None and not user["email_verified"]:
        token, expires_at = _new_verification_token()
        await set_verification_token(str(user["id"]), token, expires_at)
        await send_verification_email(user["email"], token)
    return MessageResponse(message="If that email has a pending verification, a new link has been sent.")


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> UserResponse:
    user = await fetch_user_by_id(current_user.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(
        id=str(user["id"]), email=user["email"], full_name=user["full_name"],
        email_verified=user["email_verified"],
    )
