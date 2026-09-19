from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.core.clock import utc_now
from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.models import DeadLetterJob
from app.repositories.outbox import OutboxRepository

from .health import write_heartbeat

logger = logging.getLogger(__name__)
MAX_OUTBOX_ATTEMPTS = 5


def dispatch(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "post.detected":
        from app.workers.pipeline_actors import analyze_post

        return analyze_post.send(str(payload["post_id"])).message_id
    if event_type == "comment.publish.requested":
        from app.workers.publish_actors import publish_comment

        delay = max(0, int(payload.get("delay_ms", 0)))
        return publish_comment.send_with_options(
            args=(str(payload["publish_job_id"]),), delay=delay
        ).message_id
    if event_type == "comment.reconcile.requested":
        from app.workers.publish_actors import reconcile_publish

        delay = max(0, int(payload.get("delay_ms", 0)))
        return reconcile_publish.send_with_options(
            args=(str(payload["publish_job_id"]),), delay=delay
        ).message_id
    raise ValueError(f"No outbox dispatcher for {event_type}")


async def relay_once(limit: int = 100) -> int:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            repository = OutboxRepository(session)
            events = await repository.claim_batch(limit)
            for event in events:
                try:
                    dispatch(event.event_type, event.payload)
                except Exception as exc:
                    repository.mark_failed(event, exc)
                    logger.exception("outbox dispatch failed event_id=%s", event.id)
                    if event.attempts >= MAX_OUTBOX_ATTEMPTS:
                        now = utc_now()
                        session.add(
                            DeadLetterJob(
                                source_queue="outbox",
                                actor_name=event.event_type,
                                payload={
                                    "outbox_event_id": str(event.id),
                                    "aggregate_id": str(event.aggregate_id),
                                    "event_type": event.event_type,
                                },
                                error=type(exc).__name__,
                                attempts=event.attempts,
                                first_failed_at=event.created_at,
                                last_failed_at=now,
                                trace_id=event.trace_id,
                            )
                        )
                        # Dead-lettering is terminal for the relay. Marking the
                        # source row prevents a poison event from blocking later work.
                        repository.mark_published(event)
                    continue
                repository.mark_published(event)
            return len(events)


async def run() -> None:
    from redis.asyncio import Redis

    redis = Redis.from_url(get_settings().redis_url)
    last_heartbeat = 0.0
    try:
        while True:
            now = time.time()
            if now - last_heartbeat >= 10:
                try:
                    await write_heartbeat(redis, "outbox-relay")
                    last_heartbeat = now
                except Exception:
                    logger.exception("outbox relay heartbeat failed")
            try:
                count = await relay_once()
            except Exception:
                logger.exception("outbox relay cycle failed")
                count = 0
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(0 if count else 0.25)
    finally:
        await redis.close()


if __name__ == "__main__":
    asyncio.run(run())
