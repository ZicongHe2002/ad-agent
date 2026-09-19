from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User

SENSITIVE_KEYS = {"password", "password_hash", "token", "credentials", "secret", "api_key"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(part in key.lower() for part in SENSITIVE_KEYS)
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


async def write_audit_log(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str,
    trace_id: UUID,
    actor_type: str = "SYSTEM",
    actor_id: UUID | None = None,
    tenant_id: UUID | None = None,
    resource_id: UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    if tenant_id is None and actor_type == "USER" and actor_id is not None:
        actor = await session.get(User, actor_id)
        if actor is not None:
            tenant_id = actor.tenant_id
    record = AuditLog(
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before=redact(before),
        after=redact(after),
        trace_id=trace_id,
    )
    session.add(record)
    await session.flush()
    return record
