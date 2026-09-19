from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MetricEvent

from .base import BaseRepository


class MetricRepository(BaseRepository[MetricEvent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MetricEvent)

    async def between(self, start: datetime, end: datetime) -> Sequence[MetricEvent]:
        stmt = (
            select(MetricEvent)
            .where(MetricEvent.occurred_at >= start, MetricEvent.occurred_at < end)
            .order_by(MetricEvent.occurred_at)
        )
        return (await self.session.scalars(stmt)).all()
