from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Small async repository with predictable flush semantics."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def get(self, object_id: UUID | str) -> ModelT | None:
        return await self.session.get(self.model, object_id)

    async def require(self, object_id: UUID | str) -> ModelT:
        instance = await self.get(object_id)
        if instance is None:
            raise LookupError(f"{self.model.__name__} {object_id} was not found")
        return instance

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def add_all(self, instances: Iterable[ModelT]) -> list[ModelT]:
        materialized = list(instances)
        self.session.add_all(materialized)
        await self.session.flush()
        return materialized

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        statement: Select[Any] | None = None,
    ) -> Sequence[ModelT]:
        stmt = statement if statement is not None else select(self.model)
        result = await self.session.scalars(stmt.offset(offset).limit(min(limit, 500)))
        return result.all()

    async def count(self, statement: Select[Any] | None = None) -> int:
        if statement is None:
            statement = select(func.count()).select_from(self.model)
        value = await self.session.scalar(statement)
        return int(value or 0)
