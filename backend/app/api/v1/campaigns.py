from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, is_global_admin, require_roles
from app.api.utils import audit_resource, model_dict, paginate
from app.domain.enums import CampaignStatus, RankConfidence, RunMode, UserRole
from app.models import (
    Brand,
    Campaign,
    CommentCandidate,
    CommentJob,
    CommentQualityEvaluation,
    PublishedComment,
    User,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    brand_id: UUID
    name: str = Field(min_length=1, max_length=160)
    run_mode: RunMode = RunMode.NORMAL
    start_at: datetime | None = None
    end_at: datetime | None = None
    allowed_strategies: list[str] = Field(default_factory=list)
    creator_relationship_allowlist: list[str] = Field(default_factory=list)
    max_comments_per_day: int = Field(default=20, gt=0)
    max_comments_per_creator_per_day: int = Field(default=1, gt=0)
    human_review_required: bool = True

    @model_validator(mode="after")
    def validate_values(self) -> CampaignCreate:
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if self.max_comments_per_creator_per_day > self.max_comments_per_day:
            raise ValueError("creator limit must not exceed campaign limit")
        return self


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    run_mode: RunMode | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    allowed_strategies: list[str] | None = None
    creator_relationship_allowlist: list[str] | None = None
    max_comments_per_day: int | None = Field(default=None, gt=0)
    max_comments_per_creator_per_day: int | None = Field(default=None, gt=0)
    human_review_required: bool | None = None
    publisher_kill_switch: bool | None = None


async def _brand_for_user(
    session: AsyncSession, brand_id: UUID, user: User
) -> Brand | None:
    stmt = select(Brand).where(Brand.id == brand_id)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    return cast(Brand | None, await session.scalar(stmt))


async def _campaign_for_user(
    session: AsyncSession, campaign_id: UUID, user: User
) -> Campaign | None:
    stmt = select(Campaign).join(Brand).where(Campaign.id == campaign_id)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    return cast(Campaign | None, await session.scalar(stmt))


@router.post("", status_code=201)
async def create_campaign(
    body: CampaignCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    brand = await _brand_for_user(session, body.brand_id, user)
    if brand is None:
        raise LookupError(f"Brand {body.brand_id} was not found")
    campaign = Campaign(**body.model_dump())
    session.add(campaign)
    await audit_resource(session, campaign, user, "campaign.create")
    await session.commit()
    return model_dict(campaign)


@router.get("")
async def list_campaigns(
    brand_id: UUID | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = select(Campaign).join(Brand)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    if brand_id:
        stmt = stmt.where(Campaign.brand_id == brand_id)
    stmt = stmt.order_by(Campaign.created_at.desc())
    return await paginate(session, stmt, offset=offset, limit=limit)


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: UUID,
    body: CampaignUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    campaign = await _campaign_for_user(session, campaign_id, user)
    if campaign is None:
        raise LookupError(f"Campaign {campaign_id} was not found")
    changes = body.model_dump(exclude_unset=True)
    if "publisher_kill_switch" in changes and user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only administrators may change kill switches")
    for key, value in changes.items():
        if value is None and key not in {"start_at", "end_at"}:
            raise HTTPException(status_code=422, detail=f"{key} cannot be null")
    # Validate the merged resource; validating only submitted fields misses PATCH
    # combinations such as lowering the total quota below the per-creator quota.
    CampaignCreate.model_validate({**model_dict(campaign), **changes})
    before = model_dict(campaign)
    for key, value in changes.items():
        setattr(campaign, key, value)
    from app.observability.tracing import current_trace_id
    from app.services.audit_service import write_audit_log

    await write_audit_log(
        session, action="campaign.update", resource_type="Campaign", resource_id=campaign.id,
        actor_type="USER", actor_id=user.id, tenant_id=user.tenant_id,
        trace_id=current_trace_id(), before=before, after=model_dict(campaign),
    )
    await session.commit()
    return model_dict(campaign)


@router.post("/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    campaign = await _campaign_for_user(session, campaign_id, user)
    if campaign is None:
        raise LookupError(f"Campaign {campaign_id} was not found")
    if campaign.publisher_kill_switch:
        raise HTTPException(status_code=409, detail="Campaign kill switch is enabled")
    campaign.status = CampaignStatus.ACTIVE
    await audit_resource(session, campaign, user, "campaign.activate")
    await session.commit()
    return model_dict(campaign)


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    campaign = await _campaign_for_user(session, campaign_id, user)
    if campaign is None:
        raise LookupError(f"Campaign {campaign_id} was not found")
    campaign.status = CampaignStatus.PAUSED
    await audit_resource(session, campaign, user, "campaign.pause")
    await session.commit()
    return model_dict(campaign)


@router.get("/{campaign_id}/metrics")
async def campaign_metrics(
    campaign_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if await _campaign_for_user(session, campaign_id, user) is None:
        raise LookupError(f"Campaign {campaign_id} was not found")
    from app.services.metrics_service import ranking_summary

    published = list((await session.scalars(select(PublishedComment).where(PublishedComment.campaign_id == campaign_id))).all())
    decisions = (await session.execute(select(CommentQualityEvaluation.decision, func.count()).join(
        CommentCandidate, CommentCandidate.id == CommentQualityEvaluation.candidate_id
    ).where(CommentCandidate.campaign_id == campaign_id).group_by(CommentQualityEvaluation.decision))).all()
    states = (await session.execute(select(CommentJob.state, func.count()).where(
        CommentJob.campaign_id == campaign_id
    ).group_by(CommentJob.state))).all()
    return {"campaign_id": str(campaign_id), "published": len(published),
            "jobs_by_state": {state.value: count for state, count in states},
            "quality": {decision.value: count for decision, count in decisions},
            "ranking": ranking_summary(item.chronological_rank if item.chronological_rank_confidence != RankConfidence.UNKNOWN else None for item in published)}
