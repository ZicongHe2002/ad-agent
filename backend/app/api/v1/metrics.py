from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.api.deps import get_current_user, get_db
from app.core.clock import utc_now
from app.domain.enums import CommentJobState, RankConfidence, ReviewStatus, RunMode, UserRole
from app.models import (
    Brand,
    BrandAccount,
    CommentCandidate,
    CommentJob,
    CommentQualityEvaluation,
    Creator,
    Post,
    PublishedComment,
    ReviewJob,
    RiskEvent,
    TimelineEvent,
    User,
)
from app.observability.metrics import metrics
from app.services.metrics_service import latency_summary, ranking_summary

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _tenant_filter(
    user: User,
    column: InstrumentedAttribute[UUID | None],
) -> ColumnElement[bool] | None:
    if user.role == UserRole.ADMIN and user.tenant_id is None:
        return None
    return and_(column == user.tenant_id, column.is_not(None))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.get("/overview")
async def overview(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    statement = select(CommentJob.state, func.count()).group_by(CommentJob.state)
    tenant_clause = _tenant_filter(user, CommentJob.tenant_id)
    if tenant_clause is not None:
        statement = statement.where(tenant_clause)
    states: dict[str, int] = {
        state.value: int(count)
        for state, count in (await session.execute(statement)).all()
    }
    published_statement = (
        select(func.count())
        .select_from(PublishedComment)
        .join(BrandAccount, BrandAccount.id == PublishedComment.brand_account_id)
        .join(Brand, Brand.id == BrandAccount.brand_id)
    )
    if (clause := _tenant_filter(user, Brand.tenant_id)) is not None:
        published_statement = published_statement.where(clause)
    pending_statement = (
        select(func.count())
        .select_from(ReviewJob)
        .join(CommentCandidate, CommentCandidate.id == ReviewJob.candidate_id)
        .join(CommentJob, CommentJob.id == CommentCandidate.comment_job_id)
        .where(ReviewJob.status == ReviewStatus.PENDING)
    )
    if tenant_clause is not None:
        pending_statement = pending_statement.where(tenant_clause)
    terminal = [CommentJobState.PUBLISHED, CommentJobState.FAILED, CommentJobState.BLOCKED, CommentJobState.SKIPPED]
    active_stmt = select(func.count(), func.min(CommentJob.created_at)).where(CommentJob.state.not_in(terminal))
    if tenant_clause is not None:
        active_stmt = active_stmt.where(tenant_clause)
    active_count, oldest = (await session.execute(active_stmt)).one()
    critical_count, critical_oldest = (await session.execute(active_stmt.where(CommentJob.run_mode == RunMode.FAST))).one()
    event_stmt = select(TimelineEvent.event_type, func.count()).join(
        CommentJob, CommentJob.id == TimelineEvent.comment_job_id
    ).group_by(TimelineEvent.event_type)
    if tenant_clause is not None:
        event_stmt = event_stmt.where(tenant_clause)
    activity_counts = {name: int(count) for name, count in (await session.execute(event_stmt)).all()}
    return {
        "jobs_by_state": states,
        "published_comments": int(await session.scalar(published_statement) or 0),
        "pending_reviews": int(await session.scalar(pending_statement) or 0),
        "process_counters": metrics.snapshot() if user.role == UserRole.ADMIN and user.tenant_id is None else {},
        "activity_counts": activity_counts,
        "active_jobs": int(active_count),
        "critical_active_jobs": int(critical_count),
        "oldest_active_seconds": max(0, (utc_now() - _aware(oldest)).total_seconds()) if oldest else None,
        "oldest_critical_seconds": max(0, (utc_now() - _aware(critical_oldest)).total_seconds()) if critical_oldest else None,
    }


@router.get("/latency")
async def latency(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    post_statement = (
        select(Post)
        .join(Creator, Creator.id == Post.creator_id)
        .order_by(Post.detected_at.desc())
        .limit(10_000)
    )
    if (clause := _tenant_filter(user, Creator.tenant_id)) is not None:
        post_statement = post_statement.where(clause)
    posts = list((await session.scalars(post_statement)).all())
    detection = [
        max(0.0, (_aware(item.detected_at) - _aware(item.published_at)).total_seconds() * 1000) for item in posts
    ]

    job_stmt = select(CommentJob).order_by(CommentJob.created_at.desc()).limit(10_000)
    if (clause := _tenant_filter(user, CommentJob.tenant_id)) is not None:
        job_stmt = job_stmt.where(clause)
    jobs = list((await session.scalars(job_stmt)).all())
    job_post_times: dict[UUID, datetime] = {job_id: published_at for job_id, published_at in (await session.execute(select(CommentJob.id, Post.published_at).join(Post, Post.id == CommentJob.post_id).where(
        CommentJob.id.in_([item.id for item in jobs])
    ))).all()}
    timeline_statement = (
        select(TimelineEvent)
        .where(TimelineEvent.comment_job_id.in_([item.id for item in jobs]))
        .order_by(TimelineEvent.comment_job_id, TimelineEvent.occurred_at)
    )
    events = list((await session.scalars(timeline_statement)).all())
    grouped: dict[UUID | None, dict[str, datetime]] = defaultdict(dict)
    for event in events:
        grouped[event.comment_job_id].setdefault(event.event_type, event.occurred_at)
    for job_id, created in job_post_times.items():
        grouped[job_id]["post.created"] = created
    ready_events = ("job.ready", "job.waiting_review", "job.waiting_manual_publish", "job.blocked", "job.skipped")
    for stages in grouped.values():
        ready_times = [stages[name] for name in ready_events if name in stages]
        if ready_times:
            stages["checks.completed"] = min(ready_times)

    def durations(start: str, end: str) -> list[float]:
        values: list[float] = []
        for stages in grouped.values():
            if start in stages and end in stages:
                values.append(max(0.0, (_aware(stages[end]) - _aware(stages[start])).total_seconds() * 1000))
        return values

    return {
        "unit": "milliseconds",
        "sample_scope": "latest 10000 posts and jobs",
        "detection": latency_summary(detection),
        "fetch": latency_summary(durations("job.fetching", "job.analyzing")),
        "analysis": latency_summary(durations("job.analyzing", "post.analysis.completed")),
        "generation": latency_summary(durations("job.generating", "job.quality_checking")),
        "quality": latency_summary(durations("job.quality_checking", "job.risk_checking")),
        "risk": latency_summary(durations("job.risk_checking", "checks.completed")),
        "quality_and_risk": latency_summary(durations("job.quality_checking", "checks.completed")),
        "publish": latency_summary(durations("job.publishing", "comment.published")),
        "ai_ready": latency_summary(durations("post.created", "checks.completed")),
        "end_to_end": latency_summary(durations("post.created", "comment.published")),
        "review_total": latency_summary(durations("job.waiting_review", "job.ready")),
    }


@router.get("/quality")
async def quality(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    statement = (
        select(CommentQualityEvaluation)
        .join(CommentCandidate, CommentCandidate.id == CommentQualityEvaluation.candidate_id)
        .join(CommentJob, CommentJob.id == CommentCandidate.comment_job_id)
    )
    if (clause := _tenant_filter(user, CommentJob.tenant_id)) is not None:
        statement = statement.where(clause)
    evaluations = list((await session.scalars(statement)).all())
    total = len(evaluations)
    decisions: dict[str, int] = defaultdict(int)
    for item in evaluations:
        decisions[item.decision.value] += 1

    review_statement = (
        select(ReviewJob)
        .join(CommentCandidate, CommentCandidate.id == ReviewJob.candidate_id)
        .join(CommentJob, CommentJob.id == CommentCandidate.comment_job_id)
        .where(ReviewJob.status != ReviewStatus.PENDING)
    )
    if (clause := _tenant_filter(user, CommentJob.tenant_id)) is not None:
        review_statement = review_statement.where(clause)
    reviews = list((await session.scalars(review_statement)).all())
    accepted = [
        item
        for item in reviews
        if item.status in {ReviewStatus.APPROVED, ReviewStatus.EDITED_APPROVED}
    ]
    return {
        "samples": total,
        "anchor_coverage_rate": (
            sum(float(item.anchor_coverage) > 0 for item in evaluations) / total if total else 0.0
        ),
        "quality_allow_rate": decisions["ALLOW"] / total if total else 0.0,
        "quality_review_rate": decisions["REVIEW"] / total if total else 0.0,
        "quality_block_rate": decisions["BLOCK"] / total if total else 0.0,
        "generic_comment_rate": (
            sum(item.generic_praise_detected for item in evaluations) / total if total else 0.0
        ),
        "duplicate_block_rate": (
            sum("DUPLICATE" in item.reasons for item in evaluations) / total if total else 0.0
        ),
        "human_acceptance_rate": len(accepted) / len(reviews) if reviews else 0.0,
        "human_edit_rate": (
            sum(item.status == ReviewStatus.EDITED_APPROVED for item in accepted) / len(accepted)
            if accepted
            else 0.0
        ),
    }


@router.get("/ranking")
async def ranking(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    statement = (
        select(PublishedComment)
        .join(BrandAccount, BrandAccount.id == PublishedComment.brand_account_id)
        .join(Brand, Brand.id == BrandAccount.brand_id)
    )
    if (clause := _tenant_filter(user, Brand.tenant_id)) is not None:
        statement = statement.where(clause)
    published = list((await session.scalars(statement)).all())
    chronological = ranking_summary(item.chronological_rank if item.chronological_rank_confidence != RankConfidence.UNKNOWN else None for item in published)
    visible = ranking_summary(item.visible_rank if item.visible_rank_confidence != RankConfidence.UNKNOWN else None for item in published)
    return {
        "samples": len(published),
        "first_comment_success_rate": chronological["first_comment_success_rate"],
        "top5_success_rate": chronological["top5_success_rate"],
        "chronological_rank_measurement_coverage": chronological["measurement_coverage"],
        "visible_rank_measurement_coverage": visible["measurement_coverage"],
        "chronological": chronological,
        "visible": visible,
    }


@router.get("/risk")
async def risk_metrics(session: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    stmt = select(RiskEvent).join(CommentCandidate, CommentCandidate.id == RiskEvent.candidate_id).join(
        CommentJob, CommentJob.id == CommentCandidate.comment_job_id
    )
    if (clause := _tenant_filter(user, CommentJob.tenant_id)) is not None:
        stmt = stmt.where(clause)
    events = list((await session.scalars(stmt)).all())
    decisions: dict[str, int] = defaultdict(int)
    rules: dict[str, int] = defaultdict(int)
    for event in events:
        decisions[event.final_decision.value] += 1
        for rule in set(event.matched_rules):
            rules[rule] += 1
    return {"samples": len(events), "decisions": decisions, "rule_matches": rules,
            "policy_versions": [event.policy_versions for event in events[-10:]]}
