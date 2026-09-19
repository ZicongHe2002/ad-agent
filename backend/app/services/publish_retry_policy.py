from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.domain.enums import CommentJobState
from app.domain.state_machine import can_transition, transition
from app.models import CommentJob, PublishJob
from app.services.audit_service import write_audit_log
from app.services.orchestration import transition_job, write_timeline

MAX_PUBLISH_ATTEMPTS = 5
MAX_RECONCILE_ATTEMPTS = 5
PUBLISHABLE_STATES = frozenset({CommentJobState.READY, CommentJobState.READY_FOR_RETRY})


class PublishAttemptDeferred(Exception):
    """The durable job state forbids an external publish call for this delivery."""


def retry_is_due(publish: PublishJob, now: datetime | None = None) -> bool:
    retry_at = publish.next_retry_at
    if retry_at is None:
        return True
    aware_retry_at = retry_at if retry_at.tzinfo else retry_at.replace(tzinfo=timezone.utc)
    return aware_retry_at <= (now or utc_now())


def reconciliation_attempts(publish: PublishJob) -> int:
    evidence = publish.reconciliation_evidence or {}
    if evidence.get("reconcile_publish_attempt") != publish.attempt_count:
        return 0
    value = evidence.get("reconcile_attempt_count", 0)
    return value if isinstance(value, int) and value >= 0 else 0


async def finish_publish_job(
    session: AsyncSession,
    publish: PublishJob,
    reason: str,
    *,
    blocked: bool = False,
) -> None:
    target = (
        CommentJobState.BLOCKED
        if blocked or publish.state == CommentJobState.READY
        else CommentJobState.FAILED
    )
    transition(publish, target, reason)
    publish.finished_at = utc_now()
    publish.next_retry_at = None
    publish.last_error_code = reason.lower()
    job = await session.get(CommentJob, publish.comment_job_id) if publish.comment_job_id else None
    if job is not None and can_transition(job.state, target):
        await transition_job(session, job, target, reason)
    await write_timeline(
        session,
        job=job,
        event_type=(
            "comment.publish.blocked" if target == CommentJobState.BLOCKED else "comment.publish.failed"
        ),
        aggregate_id=job.post_id if job else publish.id,
        aggregate_type="Post" if job else "PublishJob",
        payload={"publish_job_id": str(publish.id), "reason": reason},
    )
    await write_audit_log(
        session,
        action="publish.stopped",
        resource_type="PublishJob",
        resource_id=publish.id,
        actor_type="WORKER",
        trace_id=job.trace_id if job else publish.id,
        after={"state": target.value, "reason": reason, "attempt": publish.attempt_count},
    )


async def ensure_publish_attempt_allowed(session: AsyncSession, publish: PublishJob) -> None:
    if publish.state not in PUBLISHABLE_STATES:
        raise PublishAttemptDeferred("PUBLISH_NOT_READY")
    if publish.attempt_count >= MAX_PUBLISH_ATTEMPTS:
        await finish_publish_job(session, publish, "PUBLISH_ATTEMPTS_EXHAUSTED")
        raise PublishAttemptDeferred("PUBLISH_ATTEMPTS_EXHAUSTED")
    if not retry_is_due(publish):
        raise PublishAttemptDeferred("RETRY_NOT_DUE")
