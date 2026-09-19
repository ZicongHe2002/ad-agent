from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        *,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        trace_id: UUID,
        idempotency_key: str,
    ) -> OutboxEvent:
        event = OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            event_version=1,
            payload=payload,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def claim_batch(self, limit: int = 100) -> Sequence[OutboxEvent]:
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return (await self.session.scalars(stmt)).all()

    @staticmethod
    def mark_published(event: OutboxEvent) -> None:
        event.published_at = datetime.now(timezone.utc)

    @staticmethod
    def mark_failed(event: OutboxEvent, error: Exception) -> None:
        event.attempts += 1
        # Vendor exceptions can contain credentials or request bodies.
        event.last_error = type(error).__name__[:2000]
