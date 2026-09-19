from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, is_global_admin, require_roles
from app.api.utils import audit_resource, model_dict, paginate
from app.domain.enums import CreatorRelationship, MonitorState, Platform
from app.models import Creator, CreatorPlatformAccount, User

router = APIRouter(prefix="/creators", tags=["creators"])


class CreatorAccountInput(BaseModel):
    platform: Platform
    external_creator_id: str = Field(min_length=1, max_length=255)
    creator_url: str | None = None


class CreatorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=100)
    relationship_type: CreatorRelationship = CreatorRelationship.GENERAL_CREATOR
    priority: int = Field(default=50, ge=0, le=100)
    normal_poll_interval_sec: int = Field(default=600, ge=5)
    warm_poll_interval_sec: int = Field(default=60, ge=5)
    hot_poll_interval_sec: int = Field(default=10, ge=5)
    expected_publish_windows: list[dict[str, Any]] = Field(default_factory=list)
    platform_accounts: list[CreatorAccountInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_intervals(self) -> CreatorCreate:
        if (
            not self.normal_poll_interval_sec
            >= self.warm_poll_interval_sec
            >= self.hot_poll_interval_sec
        ):
            raise ValueError("poll intervals must satisfy normal >= warm >= hot")
        return self


class CreatorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    relationship_type: CreatorRelationship | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    normal_poll_interval_sec: int | None = Field(default=None, ge=5)
    warm_poll_interval_sec: int | None = Field(default=None, ge=5)
    hot_poll_interval_sec: int | None = Field(default=None, ge=5)
    expected_publish_windows: list[dict[str, Any]] | None = None


async def _creator_for_user(
    session: AsyncSession, creator_id: UUID, user: User
) -> Creator | None:
    stmt = select(Creator).where(Creator.id == creator_id)
    if not is_global_admin(user):
        stmt = stmt.where(
            Creator.tenant_id == user.tenant_id,
            Creator.tenant_id.is_not(None),
        )
    return cast(Creator | None, await session.scalar(stmt))


@router.post("", status_code=201)
async def create_creator(
    body: CreatorCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    values = body.model_dump(exclude={"platform_accounts"})
    creator = Creator(tenant_id=user.tenant_id, **values)
    session.add(creator)
    await session.flush()
    for item in body.platform_accounts:
        session.add(CreatorPlatformAccount(creator_id=creator.id, **item.model_dump()))
    await audit_resource(session, creator, user, "creator.create")
    await session.commit()
    result = model_dict(creator)
    result["platform_accounts"] = [item.model_dump(mode="json") for item in body.platform_accounts]
    return result


@router.get("")
async def list_creators(
    platform: Platform | None = None,
    relationship: CreatorRelationship | None = None,
    state: MonitorState | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = select(Creator)
    if not is_global_admin(user):
        stmt = stmt.where(
            Creator.tenant_id == user.tenant_id,
            Creator.tenant_id.is_not(None),
        )
    if relationship:
        stmt = stmt.where(Creator.relationship_type == relationship)
    if state:
        stmt = stmt.where(Creator.monitor_state == state)
    if platform:
        stmt = stmt.join(CreatorPlatformAccount).where(CreatorPlatformAccount.platform == platform)
    stmt = stmt.order_by(Creator.priority.desc(), Creator.created_at.desc())
    result = await paginate(session, stmt, offset=offset, limit=limit)
    ids = [UUID(item["id"]) for item in result["items"]]
    accounts = (await session.scalars(select(CreatorPlatformAccount).where(
        CreatorPlatformAccount.creator_id.in_(ids)
    ))).all()
    for item in result["items"]:
        item["platform_accounts"] = [
            model_dict(account) for account in accounts if str(account.creator_id) == item["id"]
        ]
    return result


@router.patch("/{creator_id}")
async def update_creator(
    creator_id: UUID,
    body: CreatorUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    creator = await _creator_for_user(session, creator_id, user)
    if creator is None:
        raise LookupError(f"Creator {creator_id} was not found")
    changes = body.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Creator fields cannot be null")
    CreatorCreate.model_validate({**model_dict(creator), **changes})
    before = model_dict(creator)
    for key, value in changes.items():
        setattr(creator, key, value)
    await audit_resource(session, creator, user, "creator.update", before=before)
    await session.commit()
    return model_dict(creator)


async def _set_monitor_state(
    creator_id: UUID,
    state: MonitorState,
    session: AsyncSession,
    user: User,
) -> dict[str, Any]:
    creator = await _creator_for_user(session, creator_id, user)
    if creator is None:
        raise LookupError(f"Creator {creator_id} was not found")
    before = model_dict(creator)
    creator.monitor_state = state
    await audit_resource(session, creator, user, "creator.monitor_state", before=before)
    await session.commit()
    return {"creator_id": str(creator.id), "monitor_state": state.value}


@router.post("/{creator_id}/monitor")
async def start_monitor(
    creator_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    return await _set_monitor_state(creator_id, MonitorState.ACTIVE, session, user)


@router.post("/{creator_id}/pause")
async def pause_monitor(
    creator_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    return await _set_monitor_state(creator_id, MonitorState.PAUSED, session, user)


@router.post("/{creator_id}/poll-now", status_code=202)
async def poll_now(
    creator_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    creator = await _creator_for_user(session, creator_id, user)
    if creator is None:
        raise LookupError(f"Creator {creator_id} was not found")
    if creator.monitor_state != MonitorState.ACTIVE:
        raise HTTPException(status_code=409, detail="Creator monitor is not active")
    from app.workers.monitor_actors import poll_creator

    message = poll_creator.send(str(creator_id))
    return {"task_id": message.message_id, "creator_id": str(creator_id)}
