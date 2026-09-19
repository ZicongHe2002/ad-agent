from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    config = settings or get_settings()
    kwargs: dict[str, object] = {
        "echo": config.database_echo,
        "pool_pre_ping": True,
    }
    if not config.database_url.startswith("sqlite+"):
        kwargs.update(
            pool_size=config.database_pool_size,
            max_overflow=config.database_max_overflow,
        )
    return create_async_engine(config.database_url, **kwargs)


engine = create_engine()
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        yield session


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    if session.in_transaction():
        async with session.begin_nested():
            yield session
    else:
        async with session.begin():
            yield session


async def dispose_engine(target: AsyncEngine | None = None) -> None:
    await (target or engine).dispose()
