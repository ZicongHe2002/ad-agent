from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from app.domain.enums import UserRole, UserStatus

from .common import APIModel, TimestampedRead


class UserCreate(APIModel):
    tenant_id: UUID | None = None
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=10, max_length=1024)
    role: UserRole = UserRole.VIEWER


class UserRead(TimestampedRead):
    tenant_id: UUID | None
    email: EmailStr
    display_name: str
    role: UserRole
    status: UserStatus
    last_login_at: datetime | None


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(APIModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int = Field(gt=0)
    user: UserRead
