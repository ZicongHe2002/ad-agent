from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import dramatiq
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.domain.enums import CommentJobState
from app.models import CommentJob, OutboxEvent, PublishJob
from app.platforms.errors import PlatformError
from app.repositories.outbox import OutboxRepository
from app.services.circuit_breaker_service import RedisCircuitBreaker
from app.services.publish_retry_policy import (
    MAX_PUBLISH_ATTEMPTS,
    MAX_RECONCILE_ATTEMPTS,
    PublishAttemptDeferred,
    ensure_publish_attempt_allowed,
    finish_publish_job,
    reconciliation_attempts,
    retry_is_due,
)
from app.services.publisher_runtime import publish_comment_job, reconcile_publish_job

from .broker import PERSISTENT_DLQ_ACTOR, QUEUE_CRITICAL, QUEUE_LOW

logger = logging.getLogger(__name__)


def _delay_until(retry_at: datetime | None, *, fallback_ms: int = 1000) -> int:
    if retry_at is None:
        return fallback_ms
    aware_retry_at = (
        retry_at if retry_at.tzinfo is not None else retry_at.replace(tzinfo=timezone.utc)
    )
    return max(0, int((aware_retry_at - utc_now()).total_seconds() * 1000))


async def _append_delivery_event(
    session: AsyncSession,
    publish: PublishJob,
    *,
    event_type: str,
    delay_ms: int,
    idempotency_key: str,
) -> bool:
    """Append a broker delivery request in the same transaction as job state."""

    existing = await session.scalar(
        select(OutboxEvent.id).where(OutboxEvent.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return False
    comment_job = (
        await session.get(CommentJob, publish.comment_job_id)
        if publish.comment_job_id is not None
        else None
    )
    await OutboxRepository(session).append(
        aggregate_type="PublishJob",
        aggregate_id=publish.id,
        event_type=event_type,
        payload={
            "publish_job_id": str(publish.id),
            "delay_ms": max(0, delay_ms),
        },
        trace_id=comment_job.trace_id if comment_job is not None else publish.id,
        idempotency_key=idempotency_key,
    )
    return True


async def _record_circuit_success(circuit: RedisCircuitBreaker) -> None:
    try:
        await circuit.record_success()
    except Exception:
        logger.exception("platform circuit success update failed")


async def _record_circuit_failure(circuit: RedisCircuitBreaker) -> None:
    try:
        await circuit.record_failure()
    except Exception:
        logger.exception("platform circuit failure update failed")


async def _close_redis(redis: Any) -> None:
    try:
        await redis.aclose()
    except AttributeError:
        await redis.close()
    except Exception:
        logger.exception("platform circuit Redis close failed")


@dramatiq.actor(
    queue_name=QUEUE_CRITICAL,
    max_retries=0,
    on_retry_exhausted=PERSISTENT_DLQ_ACTOR,
)
async def publish_comment(publish_job_id: str) -> dict[str, Any]:
    from redis.asyncio import Redis

    publish_uuid = UUID(publish_job_id)
    redis = Redis.from_url(get_settings().redis_url)
    circuit: RedisCircuitBreaker | None = None
    try:
        async with AsyncSessionFactory() as session:
            current = await session.scalar(
                select(PublishJob).where(PublishJob.id == publish_uuid).with_for_update()
            )
            if current is None:
                raise LookupError(f"PublishJob {publish_uuid} was not found")
            try:
                await ensure_publish_attempt_allowed(session, current)
            except PublishAttemptDeferred as exc:
                await session.commit()
                return {
                    "publish_job_id": publish_job_id,
                    "state": current.state.value,
                    "skipped": str(exc),
                }
            circuit = RedisCircuitBreaker(
                redis,
                current.platform.value,
                "publish_top_level_comment",
            )
            try:
                decision = await circuit.acquire()
            except Exception:
                # Circuit state is protective, not a second source of truth. The
                # durable publish state machine remains authoritative.
                logger.exception("platform circuit acquire failed; failing open")
                decision = None
            if decision is not None and not decision.allowed:
                bucket = int(time.time() // max(1, decision.retry_after_seconds))
                await _append_delivery_event(
                    session,
                    current,
                    event_type="comment.publish.requested",
                    delay_ms=decision.retry_after_seconds * 1000,
                    idempotency_key=f"circuit-publish:{current.id}:{bucket}",
                )
                await session.commit()
                return {
                    "publish_job_id": publish_job_id,
                    "state": current.state.value,
                    "skipped": "PLATFORM_CIRCUIT_OPEN",
                    "retry_after_seconds": decision.retry_after_seconds,
                }

            try:
                result = await publish_comment_job(session, publish_uuid)
                await session.commit()
            except PublishAttemptDeferred as exc:
                await session.commit()
                return {
                    "publish_job_id": publish_job_id,
                    "state": current.state.value,
                    "skipped": str(exc),
                }
            except PermissionError:
                await finish_publish_job(session, current, "PUBLISH_GATES_BLOCKED", blocked=True)
                await session.commit()
                if circuit is not None:
                    await _record_circuit_success(circuit)
                return {
                    "publish_job_id": publish_job_id,
                    "state": current.state.value,
                    "skipped": "PUBLISH_GATES_BLOCKED",
                }
            except PlatformError as exc:
                current = await session.get(PublishJob, publish_uuid)
                if exc.retryable and current is not None:
                    await _append_delivery_event(
                        session,
                        current,
                        event_type="comment.reconcile.requested",
                        delay_ms=_delay_until(current.next_retry_at),
                        idempotency_key=(
                            f"publish-reconcile:{current.id}:{current.attempt_count}"
                        ),
                    )
                await session.commit()
                if circuit is not None:
                    if exc.retryable:
                        await _record_circuit_failure(circuit)
                    else:
                        await _record_circuit_success(circuit)
                state = current.state.value if current is not None else "FAILED"
                return {
                    "publish_job_id": publish_job_id,
                    "state": state,
                    "error_code": exc.code,
                }
            except Exception:
                await session.rollback()
                if circuit is not None:
                    await _record_circuit_success(circuit)
                raise

            if circuit is not None:
                await _record_circuit_success(circuit)
            return {"published_comment_id": str(result.id)}
    finally:
        await _close_redis(redis)


@dramatiq.actor(
    queue_name=QUEUE_LOW,
    max_retries=MAX_RECONCILE_ATTEMPTS,
    min_backoff=1000,
    max_backoff=60_000,
    on_retry_exhausted=PERSISTENT_DLQ_ACTOR,
)
async def reconcile_publish(publish_job_id: str) -> dict[str, Any]:
    from redis.asyncio import Redis

    publish_uuid = UUID(publish_job_id)
    redis = Redis.from_url(get_settings().redis_url)
    circuit: RedisCircuitBreaker | None = None
    try:
        async with AsyncSessionFactory() as session:
            current = await session.scalar(
                select(PublishJob).where(PublishJob.id == publish_uuid).with_for_update()
            )
            if current is None:
                raise LookupError(f"PublishJob {publish_uuid} was not found")
            if current.state != CommentJobState.PUBLISH_UNCERTAIN:
                return {"publish_job_id": publish_job_id, "state": current.state.value}
            if reconciliation_attempts(current) >= MAX_RECONCILE_ATTEMPTS:
                await finish_publish_job(session, current, "RECONCILIATION_ATTEMPTS_EXHAUSTED")
                await session.commit()
                return {"publish_job_id": publish_job_id, "state": current.state.value}
            if not retry_is_due(current):
                return {
                    "publish_job_id": publish_job_id,
                    "state": current.state.value,
                    "skipped": "RETRY_NOT_DUE",
                }
            circuit = RedisCircuitBreaker(redis, current.platform.value, "reconcile_publish")
            try:
                decision = await circuit.acquire()
            except Exception:
                logger.exception("platform circuit acquire failed; failing open")
                decision = None
            if decision is not None and not decision.allowed:
                bucket = int(time.time() // max(1, decision.retry_after_seconds))
                await _append_delivery_event(
                    session,
                    current,
                    event_type="comment.reconcile.requested",
                    delay_ms=decision.retry_after_seconds * 1000,
                    idempotency_key=f"circuit-reconcile:{current.id}:{bucket}",
                )
                await session.commit()
                return {
                    "publish_job_id": publish_job_id,
                    "state": current.state.value,
                    "skipped": "PLATFORM_CIRCUIT_OPEN",
                    "retry_after_seconds": decision.retry_after_seconds,
                }

            try:
                result = await reconcile_publish_job(session, publish_uuid)
                if (
                    result.state == CommentJobState.READY_FOR_RETRY
                    and result.attempt_count < MAX_PUBLISH_ATTEMPTS
                ):
                    await _append_delivery_event(
                        session,
                        result,
                        event_type="comment.publish.requested",
                        delay_ms=_delay_until(result.next_retry_at),
                        idempotency_key=(
                            f"reconcile-publish:{result.id}:{result.attempt_count}"
                        ),
                    )
                await session.commit()
            except PlatformError as exc:
                await session.rollback()
                if circuit is not None:
                    if exc.retryable:
                        await _record_circuit_failure(circuit)
                    else:
                        await _record_circuit_success(circuit)
                raise
            except Exception:
                await session.rollback()
                if circuit is not None:
                    await _record_circuit_success(circuit)
                raise

            if circuit is not None:
                await _record_circuit_success(circuit)
            return {"publish_job_id": str(result.id), "state": result.state.value}
    finally:
        await _close_redis(redis)
