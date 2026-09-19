from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.domain.enums import CommentJobState, ReviewStatus
from app.domain.state_machine import transition
from app.models import (
    CommentCandidate,
    CommentJob,
    OutboxEvent,
    PublishJob,
    ReviewJob,
)
from app.repositories.outbox import OutboxRepository
from app.services.audit_service import write_audit_log
from app.services.orchestration import transition_job, write_timeline
from app.services.publish_retry_policy import (
    MAX_PUBLISH_ATTEMPTS,
    MAX_RECONCILE_ATTEMPTS,
    finish_publish_job,
    reconciliation_attempts,
)

logger = logging.getLogger(__name__)
RECOVERY_RESCAN_INTERVAL = timedelta(seconds=30)


@dataclass(frozen=True)
class MaintenanceResult:
    reconcile_publish_ids: list[UUID]
    expired_review_ids: list[UUID]
    publish_retry_ids: list[UUID] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _delivery_bucket(now: datetime) -> int:
    """Create a stable key per rescan window, while permitting later recovery."""

    return int(now.timestamp() // int(RECOVERY_RESCAN_INTERVAL.total_seconds()))


async def _append_recovery_event(
    session: AsyncSession,
    publish: PublishJob,
    *,
    event_type: str,
    now: datetime,
) -> bool:
    action = "reconcile" if event_type == "comment.reconcile.requested" else "publish"
    idempotency_key = f"maintenance-{action}:{publish.id}:{_delivery_bucket(now)}"
    existing = await session.scalar(
        select(OutboxEvent.id).where(OutboxEvent.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return False
    comment_job = (
        await session.get(CommentJob, publish.comment_job_id)
        if publish.comment_job_id
        else None
    )
    payload: dict[str, object] = {"publish_job_id": str(publish.id)}
    await OutboxRepository(session).append(
        aggregate_type="PublishJob",
        aggregate_id=publish.id,
        event_type=event_type,
        payload=payload,
        trace_id=comment_job.trace_id if comment_job else publish.id,
        idempotency_key=idempotency_key,
    )
    return True


async def recover_stuck_publishes(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    stale_after: timedelta = timedelta(minutes=2),
    limit: int = 100,
) -> list[UUID]:
    """Move abandoned external calls to reconciliation, never direct retry."""

    current = now or utc_now()
    jobs = list(
        (
            await session.scalars(
                select(PublishJob)
                .where(
                    PublishJob.state == CommentJobState.PUBLISHING,
                    PublishJob.started_at.is_not(None),
                    PublishJob.started_at <= current - stale_after,
                )
                .order_by(PublishJob.started_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    recovered: list[UUID] = []
    for publish in jobs:
        try:
            async with session.begin_nested():
                transition(publish, CommentJobState.PUBLISH_UNCERTAIN, "STUCK_PUBLISH_RECOVERY")
                publish.last_error_code = "worker_interrupted"
                publish.last_error_message = "Publishing worker did not record a terminal result"
                publish.next_retry_at = current
                comment_job = (
                    await session.get(CommentJob, publish.comment_job_id)
                    if publish.comment_job_id
                    else None
                )
                if comment_job and comment_job.state == CommentJobState.PUBLISHING:
                    await transition_job(
                        session,
                        comment_job,
                        CommentJobState.PUBLISH_UNCERTAIN,
                        "STUCK_PUBLISH_RECOVERY",
                    )
                await write_timeline(
                    session,
                    job=comment_job,
                    event_type="comment.publish.recovery_requested",
                    aggregate_id=comment_job.post_id if comment_job else publish.id,
                    aggregate_type="Post" if comment_job else "PublishJob",
                    payload={"publish_job_id": str(publish.id)},
                )
                await write_audit_log(
                    session,
                    action="publish.stuck_recovered",
                    resource_type="PublishJob",
                    resource_id=publish.id,
                    trace_id=comment_job.trace_id if comment_job else publish.id,
                    after={"state": CommentJobState.PUBLISH_UNCERTAIN.value},
                )
                await _append_recovery_event(
                    session,
                    publish,
                    event_type="comment.reconcile.requested",
                    now=current,
                )
            recovered.append(publish.id)
        except Exception:
            logger.exception("stuck publish recovery failed publish_job_id=%s", publish.id)
    return recovered


async def enqueue_due_reconciliations(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    stale_after: timedelta = RECOVERY_RESCAN_INTERVAL,
    limit: int = 100,
) -> list[UUID]:
    """Re-enqueue uncertain jobs periodically until reconciliation changes state."""

    current = now or utc_now()
    jobs = list(
        (
            await session.scalars(
                select(PublishJob)
                .where(
                    PublishJob.state == CommentJobState.PUBLISH_UNCERTAIN,
                    PublishJob.updated_at <= current - stale_after,
                    or_(
                        PublishJob.next_retry_at.is_(None),
                        PublishJob.next_retry_at <= current,
                    ),
                )
                .order_by(PublishJob.updated_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    queued: list[UUID] = []
    for publish in jobs:
        try:
            async with session.begin_nested():
                if reconciliation_attempts(publish) >= MAX_RECONCILE_ATTEMPTS:
                    await finish_publish_job(session, publish, "RECONCILIATION_ATTEMPTS_EXHAUSTED")
                    continue
                await _append_recovery_event(
                    session,
                    publish,
                    event_type="comment.reconcile.requested",
                    now=current,
                )
            queued.append(publish.id)
        except Exception:
            logger.exception("reconciliation recovery enqueue failed publish_job_id=%s", publish.id)
    return queued


async def enqueue_due_publish_retries(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    stale_after: timedelta = RECOVERY_RESCAN_INTERVAL,
    limit: int = 100,
) -> list[UUID]:
    """Recover READY work whose original outbox/broker delivery was lost."""

    current = now or utc_now()
    old_enough = PublishJob.updated_at <= current - stale_after
    due_retry = or_(PublishJob.next_retry_at.is_(None), PublishJob.next_retry_at <= current)
    jobs = list(
        (
            await session.scalars(
                select(PublishJob)
                .where(
                    or_(
                        and_(PublishJob.state == CommentJobState.READY, old_enough, due_retry),
                        and_(
                            PublishJob.state == CommentJobState.READY_FOR_RETRY,
                            old_enough,
                            due_retry,
                        ),
                    )
                )
                .order_by(PublishJob.updated_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    queued: list[UUID] = []
    for publish in jobs:
        try:
            async with session.begin_nested():
                if publish.attempt_count >= MAX_PUBLISH_ATTEMPTS:
                    await finish_publish_job(session, publish, "PUBLISH_ATTEMPTS_EXHAUSTED")
                    continue
                await _append_recovery_event(
                    session,
                    publish,
                    event_type="comment.publish.requested",
                    now=current,
                )
            queued.append(publish.id)
        except Exception:
            logger.exception("publish recovery enqueue failed publish_job_id=%s", publish.id)
    return queued


async def expire_stale_reviews(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> list[UUID]:
    current = now or utc_now()
    reviews = list(
        (
            await session.scalars(
                select(ReviewJob)
                .where(
                    ReviewJob.status == ReviewStatus.PENDING,
                    ReviewJob.expires_at.is_not(None),
                    ReviewJob.expires_at <= current,
                )
                .order_by(ReviewJob.expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    expired: list[UUID] = []
    for review in reviews:
        try:
            async with session.begin_nested():
                review.status = ReviewStatus.EXPIRED
                review.resolved_at = current
                review.review_notes = "Expired automatically before a human decision"
                candidate = await session.get(CommentCandidate, review.candidate_id)
                comment_job = (
                    await session.get(CommentJob, candidate.comment_job_id)
                    if candidate and candidate.comment_job_id
                    else None
                )
                if comment_job and comment_job.state == CommentJobState.WAITING_REVIEW:
                    await transition_job(
                        session,
                        comment_job,
                        CommentJobState.SKIPPED,
                        "REVIEW_EXPIRED",
                    )
            expired.append(review.id)
        except Exception:
            logger.exception("stale review expiry failed review_job_id=%s", review.id)
    return expired


async def run_maintenance_once(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> MaintenanceResult:
    current = now or utc_now()
    errors: list[str] = []

    async def isolated(
        name: str,
        operation: Callable[[], Awaitable[list[UUID]]],
    ) -> list[UUID]:
        try:
            async with session.begin_nested():
                return await operation()
        except Exception:
            logger.exception("maintenance operation failed operation=%s", name)
            errors.append(name)
            return []

    recovered = await isolated(
        "recover_stuck_publishes",
        lambda: recover_stuck_publishes(session, now=current),
    )
    uncertain = await isolated(
        "enqueue_due_reconciliations",
        lambda: enqueue_due_reconciliations(session, now=current),
    )
    retries = await isolated(
        "enqueue_due_publish_retries",
        lambda: enqueue_due_publish_retries(session, now=current),
    )
    expired = await isolated(
        "expire_stale_reviews",
        lambda: expire_stale_reviews(session, now=current),
    )
    reconcile_ids = list(dict.fromkeys([*recovered, *uncertain]))
    return MaintenanceResult(
        reconcile_publish_ids=reconcile_ids,
        expired_review_ids=expired,
        publish_retry_ids=retries,
        errors=errors,
    )
