from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, is_global_admin, require_roles
from app.api.utils import model_dict, paginate
from app.domain.enums import CandidateStatus, CommentJobState, DisclosureStatus, Platform
from app.models import (
    Brand,
    BrandAccount,
    Campaign,
    CommentCandidate,
    PublishedComment,
    PublishJob,
    User,
)


def _publish_statement(user: User) -> Select[tuple[PublishJob]]:
    stmt = select(PublishJob).join(BrandAccount, BrandAccount.id == PublishJob.brand_account_id).join(
        Brand, Brand.id == BrandAccount.brand_id
    )
    if not is_global_admin(user):
        stmt = stmt.where(Brand.tenant_id == user.tenant_id, Brand.tenant_id.is_not(None))
    return stmt

router = APIRouter(prefix="/comments", tags=["comments"])


class RegenerateInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ManualResultInput(BaseModel):
    result: str = Field(pattern="^(published|skipped|failed)$")
    external_comment_id: str | None = None
    operator_confirmed: bool = False
    disclosure_status: DisclosureStatus | None = None
    disclosure_evidence: dict[str, Any] | None = None


@router.get("/publish-jobs")
async def list_publish_jobs(
    state: CommentJobState | None = None, offset: int = 0, limit: int = 100,
    session: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = _publish_statement(user).order_by(PublishJob.created_at.desc())
    if state:
        stmt = stmt.where(PublishJob.state == state)
    return await paginate(session, stmt, offset=offset, limit=limit)


@router.get("/publish-jobs/{publish_job_id}")
async def publish_job_detail(
    publish_job_id: UUID,
    session: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    job = await session.scalar(_publish_statement(user).where(PublishJob.id == publish_job_id))
    if job is None:
        raise LookupError(f"PublishJob {publish_job_id} was not found")
    candidate = await session.get(CommentCandidate, job.candidate_id)
    from app.services.presentation_service import candidate_context

    return {
        **model_dict(job), "candidate": model_dict(candidate) if candidate else None,
        **(await candidate_context(session, candidate) if candidate else {}),
    }


@router.get("/candidates")
async def list_candidates(
    status: CandidateStatus | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = (
        select(CommentCandidate)
        .join(Campaign, Campaign.id == CommentCandidate.campaign_id)
        .join(Brand, Brand.id == Campaign.brand_id)
    )
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    if status:
        stmt = stmt.where(CommentCandidate.status == status)
    stmt = stmt.order_by(CommentCandidate.created_at.desc())
    return await paginate(session, stmt, offset=offset, limit=limit)


@router.get("/published")
async def list_published(
    platform: Platform | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = (
        select(PublishedComment)
        .join(BrandAccount, BrandAccount.id == PublishedComment.brand_account_id)
        .join(Brand, Brand.id == BrandAccount.brand_id)
    )
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    if platform:
        stmt = stmt.where(PublishedComment.platform == platform)
    stmt = stmt.order_by(PublishedComment.published_at.desc())
    return await paginate(session, stmt, offset=offset, limit=limit)


@router.post("/candidates/{candidate_id}/regenerate", status_code=202)
async def regenerate_candidate(
    candidate_id: UUID,
    body: RegenerateInput,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER", "REVIEWER")),
) -> dict[str, Any]:
    statement = (
        select(CommentCandidate)
        .join(Campaign, Campaign.id == CommentCandidate.campaign_id)
        .join(Brand, Brand.id == Campaign.brand_id)
        .where(CommentCandidate.id == candidate_id)
    )
    if not is_global_admin(user):
        statement = statement.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    candidate = await session.scalar(statement)
    if candidate is None:
        raise LookupError(f"CommentCandidate {candidate_id} was not found")
    if candidate.comment_job_id is None:
        raise HTTPException(status_code=409, detail="Candidate has no pipeline job")
    from app.workers.pipeline_actors import regenerate_comments

    message = regenerate_comments.send(str(candidate.comment_job_id), body.reason)
    return {"task_id": message.message_id, "comment_job_id": str(candidate.comment_job_id)}


@router.post("/publish-jobs/{publish_job_id}/reconcile", status_code=202)
async def reconcile_comment(
    publish_job_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER", "REVIEWER")),
) -> dict[str, Any]:
    statement = (
        select(PublishJob)
        .join(BrandAccount, BrandAccount.id == PublishJob.brand_account_id)
        .join(Brand, Brand.id == BrandAccount.brand_id)
        .where(PublishJob.id == publish_job_id)
    )
    if not is_global_admin(user):
        statement = statement.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    if await session.scalar(statement) is None:
        raise LookupError(f"PublishJob {publish_job_id} was not found")
    from app.workers.publish_actors import reconcile_publish

    message = reconcile_publish.send(str(publish_job_id))
    return {"task_id": message.message_id, "publish_job_id": str(publish_job_id)}


@router.post("/publish-jobs/{publish_job_id}/manual-result")
async def confirm_manual_result(
    publish_job_id: UUID,
    body: ManualResultInput,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER", "REVIEWER")),
) -> dict[str, Any]:
    statement = (
        select(PublishJob)
        .join(BrandAccount, BrandAccount.id == PublishJob.brand_account_id)
        .join(Brand, Brand.id == BrandAccount.brand_id)
        .where(PublishJob.id == publish_job_id)
    )
    if not is_global_admin(user):
        statement = statement.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    if await session.scalar(statement) is None:
        raise LookupError(f"PublishJob {publish_job_id} was not found")

    from app.services.orchestration import confirm_manual_publish

    result = await confirm_manual_publish(
        session, publish_job_id, body.result, body.external_comment_id,
        operator_id=user.id, operator_confirmed=body.operator_confirmed,
        disclosure_status=body.disclosure_status, disclosure_evidence=body.disclosure_evidence,
    )
    await session.commit()
    return result
