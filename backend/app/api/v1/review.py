from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, is_global_admin, require_roles
from app.api.utils import model_dict, paginate
from app.core.clock import utc_now
from app.domain.enums import DisclosureStatus, ReviewStatus
from app.models import (
    Brand,
    Campaign,
    CommentCandidate,
    CommentQualityEvaluation,
    PostAnchor,
    ReviewJob,
    RiskEvent,
    User,
)

router = APIRouter(prefix="/review/jobs", tags=["review"])


class ReviewNotes(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)
    disclosure_status: DisclosureStatus | None = None
    disclosure_evidence: dict[str, Any] | None = None


class EditApproval(ReviewNotes):
    final_text: str = Field(min_length=1, max_length=1000)
    edit_reason: str = Field(min_length=3, max_length=1000)


class CandidateSelection(BaseModel):
    candidate_id: UUID


def _review_statement(job_id: UUID | None, user: User) -> Select[tuple[ReviewJob]]:
    statement = (
        select(ReviewJob)
        .join(CommentCandidate, CommentCandidate.id == ReviewJob.candidate_id)
        .join(Campaign, Campaign.id == CommentCandidate.campaign_id)
        .join(Brand, Brand.id == Campaign.brand_id)
    )
    if job_id is not None:
        statement = statement.where(ReviewJob.id == job_id)
    if not is_global_admin(user):
        statement = statement.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    return statement


async def _get_review_for_user(
    session: AsyncSession,
    job_id: UUID,
    user: User,
    *,
    for_update: bool = False,
) -> ReviewJob:
    statement = _review_statement(job_id, user)
    if for_update:
        statement = statement.with_for_update(of=ReviewJob)
    job = await session.scalar(statement)
    if job is None:
        raise LookupError(f"ReviewJob {job_id} was not found")
    return job


@router.get("")
async def list_review_jobs(
    status: ReviewStatus = ReviewStatus.PENDING,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = _review_statement(None, user).where(ReviewJob.status == status)
    stmt = stmt.order_by(ReviewJob.submitted_at)
    return await paginate(session, stmt, offset=offset, limit=limit)


@router.get("/{job_id}")
async def review_detail(
    job_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    job = await _get_review_for_user(session, job_id, user)
    candidate = await session.get(CommentCandidate, job.candidate_id)
    quality = await session.scalar(
        select(CommentQualityEvaluation).where(
            CommentQualityEvaluation.candidate_id == job.candidate_id
        )
    )
    risks = (
        await session.scalars(
            select(RiskEvent)
            .where(RiskEvent.candidate_id == job.candidate_id)
            .order_by(RiskEvent.created_at)
        )
    ).all()
    anchors: list[PostAnchor] = []
    if candidate:
        anchors = list(
            (
                await session.scalars(
                    select(PostAnchor).where(PostAnchor.post_id == candidate.post_id)
                )
            ).all()
        )
    return {
        **(await _candidate_context(session, candidate) if candidate else {}),
        **model_dict(job),
        "candidate": model_dict(candidate) if candidate else None,
        "quality": model_dict(quality) if quality else None,
        "risk_events": [model_dict(item) for item in risks],
        "anchors": [model_dict(item) for item in anchors],
    }


async def _candidate_context(session: AsyncSession, candidate: CommentCandidate) -> dict[str, Any]:
    from app.services.presentation_service import candidate_context

    return await candidate_context(session, candidate)


@router.post("/{job_id}/claim")
async def claim_review(
    job_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "REVIEWER")),
) -> dict[str, Any]:
    job = await _get_review_for_user(session, job_id, user, for_update=True)
    from datetime import timezone

    expiry = job.expires_at
    if expiry and (expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)) <= utc_now():
        raise HTTPException(status_code=409, detail="Review job has expired")
    if job.status.value != "PENDING" or (job.assigned_to and job.assigned_to != user.id):
        raise HTTPException(status_code=409, detail="Review job is unavailable")
    job.assigned_to = user.id
    await session.commit()
    return model_dict(job)


@router.post("/{job_id}/approve")
async def approve_review(
    job_id: UUID,
    body: ReviewNotes,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "REVIEWER")),
) -> dict[str, Any]:
    await _get_review_for_user(session, job_id, user)
    from app.services.orchestration import resolve_review

    result = await resolve_review(
        session, job_id, user.id, action="approve", notes=body.notes,
        disclosure_status=body.disclosure_status, disclosure_evidence=body.disclosure_evidence,
    )
    await session.commit()
    return result


@router.post("/{job_id}/select-candidate")
async def select_candidate(
    job_id: UUID, body: CandidateSelection,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "REVIEWER")),
) -> dict[str, Any]:
    await _get_review_for_user(session, job_id, user)
    from app.services.orchestration import select_review_candidate

    result = await select_review_candidate(session, job_id, body.candidate_id, user.id)
    await session.commit()
    return result


@router.post("/{job_id}/edit-and-approve")
async def edit_and_approve_review(
    job_id: UUID,
    body: EditApproval,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "REVIEWER")),
) -> dict[str, Any]:
    await _get_review_for_user(session, job_id, user)
    from app.services.orchestration import resolve_review

    result = await resolve_review(
        session,
        job_id,
        user.id,
        action="edit-and-approve",
        final_text=body.final_text,
        notes=body.edit_reason,
        disclosure_status=body.disclosure_status,
        disclosure_evidence=body.disclosure_evidence,
    )
    await session.commit()
    return result


@router.post("/{job_id}/reject")
async def reject_review(
    job_id: UUID,
    body: ReviewNotes,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "REVIEWER")),
) -> dict[str, Any]:
    await _get_review_for_user(session, job_id, user)
    from app.services.orchestration import resolve_review

    result = await resolve_review(session, job_id, user.id, action="reject", notes=body.notes)
    await session.commit()
    return result
