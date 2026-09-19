from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import AsyncIO

from app.core.config import get_settings

from .health import WorkerHeartbeatMiddleware

settings = get_settings()
broker = RedisBroker(url=settings.redis_url)  # type: ignore[no-untyped-call]
if not any(type(item).__name__ == "AsyncIO" for item in broker.middleware):
    broker.add_middleware(AsyncIO())
if not any(type(item).__name__ == "WorkerHeartbeatMiddleware" for item in broker.middleware):
    broker.add_middleware(WorkerHeartbeatMiddleware())
dramatiq.set_broker(broker)


QUEUE_CRITICAL = "critical"
QUEUE_HIGH = "high"
QUEUE_NORMAL = "normal"
QUEUE_LOW = "low"
PERSISTENT_DLQ_ACTOR = "persist_dead_letter"


@dramatiq.actor(queue_name=QUEUE_LOW, max_retries=5)
async def persist_dead_letter(
    message_data: dict[str, Any],
    retry_data: dict[str, Any],
) -> None:
    """Persist exhausted key actors without copying their potentially secret args."""

    from sqlalchemy import select

    from app.core.clock import utc_now
    from app.db.session import AsyncSessionFactory
    from app.models import DeadLetterJob

    message_id = str(message_data.get("message_id", "unknown"))
    trace_id = uuid5(NAMESPACE_URL, f"dramatiq:{message_id}")
    async with AsyncSessionFactory() as session:
        existing = await session.scalar(
            select(DeadLetterJob.id).where(
                DeadLetterJob.trace_id == trace_id,
                DeadLetterJob.actor_name == str(message_data.get("actor_name", "unknown")),
            )
        )
        if existing is not None:
            return
        timestamp_ms = int(message_data.get("message_timestamp", 0) or 0)
        first_failed_at = (
            datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            if timestamp_ms > 0
            else utc_now()
        )
        session.add(
            DeadLetterJob(
                source_queue=str(message_data.get("queue_name", "unknown")),
                actor_name=str(message_data.get("actor_name", "unknown")),
                payload={"message_id": message_id},
                error="RetriesExhausted",
                attempts=max(1, int(retry_data.get("retries", 1))),
                first_failed_at=first_failed_at,
                last_failed_at=utc_now(),
                trace_id=trace_id,
            )
        )
        await session.commit()
