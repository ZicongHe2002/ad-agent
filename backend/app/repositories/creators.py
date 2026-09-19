from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Creator, CreatorPlatformAccount

from .base import BaseRepository


class CreatorRepository(BaseRepository[Creator]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Creator)


class CreatorPlatformAccountRepository(BaseRepository[CreatorPlatformAccount]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CreatorPlatformAccount)
