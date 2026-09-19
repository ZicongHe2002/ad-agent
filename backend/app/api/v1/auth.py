from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.utils import model_dict
from app.core.clock import utc_now
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.models import User
from app.observability.tracing import current_trace_id
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: str


def _refresh_token(user: User) -> str:
    settings = get_settings()
    now = utc_now()
    return jwt.encode(
        {
            "sub": str(user.id),
            "type": "refresh",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=7)).timestamp()),
        },
        settings.app_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def _tokens(user: User) -> dict[str, Any]:
    settings = get_settings()
    access = create_access_token(
        subject=user.id,
        secret=settings.app_secret_key.get_secret_value(),
        expires_delta=timedelta(minutes=settings.access_token_ttl_minutes),
        algorithm=settings.jwt_algorithm,
        extra_claims={"role": user.role.value},
    )
    return {
        "access_token": access,
        "refresh_token": _refresh_token(user),
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_minutes * 60,
        "user": model_dict(user),
    }


@router.post("/login")
async def login(
    body: LoginRequest, session: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    user = await session.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        await write_audit_log(
            session,
            action="failed_login",
            resource_type="User",
            trace_id=current_trace_id(),
            after={"email": body.email.lower()},
        )
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    user.last_login_at = utc_now()
    await write_audit_log(
        session,
        action="login",
        resource_type="User",
        resource_id=user.id,
        actor_type="USER",
        actor_id=user.id,
        trace_id=current_trace_id(),
    )
    await session.commit()
    await session.refresh(user)
    return _tokens(user)


@router.post("/refresh")
async def refresh(
    body: RefreshRequest, session: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    settings = get_settings()
    try:
        claims = jwt.decode(
            body.refresh_token,
            settings.app_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
        if claims.get("type") != "refresh":
            raise jwt.InvalidTokenError("invalid token type")
        user = await session.get(User, UUID(str(claims["sub"])))
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return _tokens(user)


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return model_dict(user)
