from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_session
from app.domain.enums import TenantStatus, UserRole
from app.models import Tenant, User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    settings = get_settings()
    try:
        claims = decode_access_token(
            credentials.credentials,
            secret=settings.app_secret_key.get_secret_value(),
            algorithm=settings.jwt_algorithm,
        )
        user_id = UUID(str(claims["sub"]))
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    if user.tenant_id is None and user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="A tenant membership is required")
    if user.tenant_id is not None:
        tenant = await session.get(Tenant, user.tenant_id)
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="Tenant is not active")
    return user


def require_roles(*roles: str) -> Callable[..., Awaitable[User]]:
    allowed = set(roles)

    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency


def is_global_admin(user: User) -> bool:
    """Return whether a user may access resources across tenant boundaries."""

    return user.role is UserRole.ADMIN and user.tenant_id is None


async def require_global_admin(user: User = Depends(get_current_user)) -> User:
    if not is_global_admin(user):
        raise HTTPException(status_code=403, detail="Global administrator role required")
    return user
