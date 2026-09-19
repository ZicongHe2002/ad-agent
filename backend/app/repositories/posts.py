from __future__ import annotations

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Post

from .base import BaseRepository


class PostRepository(BaseRepository[Post]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Post)

    async def by_external_id(self, platform: str, external_post_id: str) -> Post | None:
        stmt = select(Post).where(
            Post.platform == platform,
            Post.external_post_id == external_post_id,
        )
        return cast(Post | None, await self.session.scalar(stmt))

    async def for_creator(self, creator_id: UUID, limit: int = 100) -> Sequence[Post]:
        stmt = (
            select(Post)
            .where(Post.creator_id == creator_id)
            .order_by(Post.published_at.desc())
            .limit(limit)
        )
        return (await self.session.scalars(stmt)).all()
