from __future__ import annotations

import os

import pytest_asyncio

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////private/tmp/firstcomment-tests.sqlite")
os.environ.setdefault("LOG_JSON", "false")


@pytest_asyncio.fixture
async def clean_database():
    import app.models  # noqa: F401
    from app.db.base import Base
    from app.db.session import AsyncSessionFactory, engine

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield AsyncSessionFactory
    await engine.dispose()
