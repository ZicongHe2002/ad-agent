from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TimelineEvent


class TimelineWriter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def write(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        trace_id: UUID,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> TimelineEvent:
        event = TimelineEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            trace_id=trace_id,
            payload=payload or {},
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )
        self.session.add(event)
        await self.session.flush()
        return event
