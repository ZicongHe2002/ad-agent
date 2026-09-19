from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sqlalchemy_inspect


def json_value(value: Any) -> Any:
    if isinstance(value, (UUID, datetime, date)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return "[encrypted]"
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    return value


def model_dict(instance: Any, *, exclude: set[str] | None = None) -> dict[str, Any]:
    hidden = {"password_hash", "credentials_ciphertext", "credentials_nonce"} | (exclude or set())
    mapper = sqlalchemy_inspect(instance).mapper
    return {
        column.key: json_value(getattr(instance, column.key))
        for column in mapper.column_attrs
        if column.key not in hidden
    }


def page(
    items: Iterable[Any], *, total: int | None = None, offset: int = 0, limit: int = 100
) -> dict[str, Any]:
    materialized = list(items)
    return {
        "items": [model_dict(item) for item in materialized],
        "total": len(materialized) if total is None else total,
        "offset": offset,
        "limit": limit,
    }


async def paginate(
    session: AsyncSession, statement: Select[Any], *, offset: int = 0, limit: int = 100
) -> dict[str, Any]:
    if offset < 0 or not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="offset must be >= 0 and limit between 1 and 500")
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    items = (await session.scalars(statement.offset(offset).limit(limit))).all()
    return page(items, total=total or 0, offset=offset, limit=limit)


async def audit_resource(
    session: AsyncSession, instance: Any, user: Any, action: str,
    *, before: dict[str, Any] | None = None,
) -> None:
    from app.observability.tracing import current_trace_id
    from app.services.audit_service import write_audit_log

    await session.flush()
    await write_audit_log(
        session, action=action, resource_type=type(instance).__name__, resource_id=instance.id,
        actor_type="USER", actor_id=user.id, tenant_id=user.tenant_id,
        trace_id=current_trace_id(), before=before, after=model_dict(instance),
    )
