from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, MetaData, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.core.ids import new_uuid

from .naming import NAMING_CONVENTION

JSONType = JSON().with_variant(JSONB(), "postgresql")


def enum_type(enum_class: type[enum.Enum], *, name: str | None = None) -> SAEnum:
    enum_name = name or f"{enum_class.__name__.lower()}_enum"
    max_length = max(len(str(member.value)) for member in enum_class)
    return SAEnum(
        enum_class,
        name=enum_name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=max_length,
        values_callable=lambda members: [str(member.value) for member in members],
    )


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Async serializers must not trigger implicit IO for server-generated values
    # after UPDATE (notably TimestampMixin.updated_at).
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 -- SQLAlchemy mapping declaration

    @declared_attr.directive
    def __tablename__(cls) -> str:
        name = cls.__name__
        return (
            "".join(f"_{char.lower()}" if char.isupper() else char for char in name).lstrip("_")
            + "s"
        )


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AggregateMixin(UUIDPrimaryKeyMixin, TimestampMixin):
    pass
