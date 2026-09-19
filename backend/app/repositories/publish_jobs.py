from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PublishJob

from .base import BaseRepository


class PublishJobRepository(BaseRepository[PublishJob]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PublishJob)

    async def by_idempotency_key(self, key: str) -> PublishJob | None:
        return cast(
            PublishJob | None,
            await self.session.scalar(
                select(PublishJob).where(PublishJob.idempotency_key == key)
            ),
        )
