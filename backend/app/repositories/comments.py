from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CommentCandidate, PublishedComment

from .base import BaseRepository


class CommentCandidateRepository(BaseRepository[CommentCandidate]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CommentCandidate)


class PublishedCommentRepository(BaseRepository[PublishedComment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PublishedComment)

    async def recent_texts(
        self,
        *,
        brand_account_id: UUID,
        campaign_id: UUID | None = None,
        creator_id: UUID | None = None,
        limit: int = 220,
    ) -> Sequence[str]:
        clauses = [PublishedComment.brand_account_id == brand_account_id]
        optional = []
        if campaign_id is not None and hasattr(PublishedComment, "campaign_id"):
            optional.append(PublishedComment.campaign_id == campaign_id)
        if creator_id is not None and hasattr(PublishedComment, "creator_id"):
            optional.append(PublishedComment.creator_id == creator_id)
        where = or_(*optional) if optional else clauses[0]
        stmt = (
            select(PublishedComment.final_text)
            .where(or_(clauses[0], where))
            .order_by(PublishedComment.published_at.desc())
            .limit(limit)
        )
        return (await self.session.scalars(stmt)).all()
