from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_global_admin
from app.core.config import get_settings
from app.domain.enums import CapabilityName, CapabilityStatus, Platform
from app.models import CapabilityRecord, User
from app.observability.tracing import current_trace_id
from app.services.audit_service import write_audit_log
from app.services.capability_service import effective_capabilities

router = APIRouter(prefix="/system", tags=["system"])


class CapabilityUpdate(BaseModel):
    status: CapabilityStatus
    source_title: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None, max_length=2048)
    source_owner: str | None = Field(default=None, max_length=160)
    scope: dict[str, object] = Field(default_factory=dict)
    conditions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    verified_at: datetime | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def evidence_for_verified_status(self) -> CapabilityUpdate:
        if self.status in {CapabilityStatus.SUPPORTED, CapabilityStatus.CONDITIONAL}:
            if not self.source_title or not self.source_owner or not self.verified_at:
                raise ValueError("Verified capabilities require title, owner, and verified_at")
        return self


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "firstcomment-agent",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/readiness")
async def readiness(response: Response, session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    from app.workers.health import RUNTIME_HEARTBEAT_NAMES, heartbeat_status

    checks: dict[str, bool] = {"postgresql": False, "redis": False}
    workers = dict.fromkeys(RUNTIME_HEARTBEAT_NAMES, False)
    try:
        await session.execute(text("SELECT 1"))
        checks["postgresql"] = True
    except Exception:
        checks["postgresql"] = False
    try:
        from redis.asyncio import Redis

        async with Redis.from_url(
            str(get_settings().redis_url), socket_connect_timeout=2, socket_timeout=2
        ) as redis:
            checks["redis"] = bool(await redis.ping())
            workers = await heartbeat_status(redis, list(RUNTIME_HEARTBEAT_NAMES))
    except Exception:
        checks["redis"] = False
    checks["workers"] = all(workers.values())
    ready = all(checks.values())
    response.status_code = 200 if ready else 503
    return {"ready": ready, "checks": checks, "workers": workers}


@router.get("/queues")
async def queue_depths(_user: User = Depends(require_global_admin)) -> dict[str, int | None]:
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(str(get_settings().redis_url))
        values: dict[str, int | None] = {}
        for name in ("critical", "high", "normal", "low"):
            values[name] = int(await redis.llen(f"dramatiq:{name}"))
        await redis.close()
        return values
    except Exception:
        return {name: None for name in ("critical", "high", "normal", "low")}


@router.get("/capabilities")
async def capability_matrix(
    session: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    platforms: list[dict[str, Any]] = []
    for platform in Platform:
        effective, records = await effective_capabilities(session, platform)
        by_name = {item.capability: item for item in records}
        capabilities: list[dict[str, Any]] = []
        for name in CapabilityName:
            record = by_name.get(name)
            capabilities.append(
                {
                    "capability": name.value,
                    "status": effective.status_for(name).value,
                    "record_id": str(record.id) if record else None,
                    "source_title": record.source_title if record else None,
                    "source_url": record.source_url if record else None,
                    "source_owner": record.source_owner if record else None,
                    "scope": record.scope if record else {},
                    "conditions": record.conditions if record else [],
                    "limitations": record.limitations if record else [],
                    "verified_at": record.verified_at if record else None,
                    "expires_at": record.expires_at if record else None,
                }
            )
        platforms.append({"platform": platform.value, "capabilities": capabilities})
    return {"platforms": platforms}


@router.put("/capabilities/{platform}/{capability}")
async def update_capability(
    platform: Platform,
    capability: CapabilityName,
    body: CapabilityUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_global_admin),
) -> dict[str, Any]:
    record = await session.scalar(
        select(CapabilityRecord).where(
            CapabilityRecord.platform == platform,
            CapabilityRecord.capability == capability,
        )
    )
    before = {"status": record.status.value} if record else None
    values = body.model_dump()
    if record is None:
        record = CapabilityRecord(
            tenant_id=user.tenant_id,
            platform=platform,
            capability=capability,
            verified_by_user_id=user.id,
            **values,
        )
        session.add(record)
    else:
        for key, value in values.items():
            setattr(record, key, value)
        record.verified_by_user_id = user.id
    await session.flush()
    await write_audit_log(
        session,
        action="capability.change",
        resource_type="CapabilityRecord",
        resource_id=record.id,
        actor_type="USER",
        actor_id=user.id,
        trace_id=current_trace_id(),
        before=before,
        after={"status": record.status.value, "platform": platform.value},
    )
    await session.commit()
    return {"id": str(record.id), "platform": platform.value, **body.model_dump(mode="json")}


@router.post("/publishers/{platform}/disable")
async def disable_publisher(
    platform: Platform,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_global_admin),
) -> dict[str, Any]:
    record = await session.scalar(
        select(CapabilityRecord).where(
            CapabilityRecord.platform == platform,
            CapabilityRecord.capability == CapabilityName.TOP_LEVEL_COMMENT,
        )
    )
    before = record.status.value if record else None
    if record is None:
        record = CapabilityRecord(
            tenant_id=user.tenant_id,
            platform=platform,
            capability=CapabilityName.TOP_LEVEL_COMMENT,
            status=CapabilityStatus.DISABLED,
            verified_by_user_id=user.id,
        )
        session.add(record)
    else:
        record.status = CapabilityStatus.DISABLED
        record.verified_by_user_id = user.id
    await session.flush()
    await write_audit_log(
        session,
        action="publisher.kill_switch.disable",
        resource_type="Platform",
        actor_type="USER",
        actor_id=user.id,
        trace_id=current_trace_id(),
        before={"status": before},
        after={"platform": platform.value, "status": CapabilityStatus.DISABLED.value},
    )
    await session.commit()
    return {"platform": platform.value, "publisher_disabled": True}
