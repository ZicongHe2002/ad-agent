from __future__ import annotations

from typing import Any
from uuid import UUID

import dramatiq

from app.db.session import AsyncSessionFactory
from app.domain.enums import RunMode
from app.services.pipeline_service import analyze_post as analyze_post_service
from app.services.pipeline_service import regenerate_comment_job

from .broker import PERSISTENT_DLQ_ACTOR, QUEUE_HIGH, QUEUE_NORMAL


@dramatiq.actor(
    queue_name=QUEUE_HIGH,
    max_retries=2,
    min_backoff=500,
    max_backoff=10_000,
    on_retry_exhausted=PERSISTENT_DLQ_ACTOR,
)
async def analyze_post(post_id: str, mode: str | None = None) -> dict[str, Any]:
    async with AsyncSessionFactory() as session:
        try:
            jobs = await analyze_post_service(
                session, UUID(post_id), RunMode(mode) if mode else None
            )
            await session.commit()
            return {"post_id": post_id, "job_ids": [str(item.id) for item in jobs]}
        except Exception:
            await session.rollback()
            raise


@dramatiq.actor(
    queue_name=QUEUE_NORMAL,
    max_retries=1,
    on_retry_exhausted=PERSISTENT_DLQ_ACTOR,
)
async def regenerate_comments(comment_job_id: str, reason: str) -> dict[str, Any]:
    async with AsyncSessionFactory() as session:
        try:
            job = await regenerate_comment_job(session, UUID(comment_job_id), reason)
            await session.commit()
            return {"comment_job_id": str(job.id), "state": job.state.value}
        except Exception:
            await session.rollback()
            raise
