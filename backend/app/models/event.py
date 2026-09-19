from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType


class OutboxEvent(AggregateMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("length(trim(aggregate_type)) > 0", name="aggregate_type_nonempty"),
        CheckConstraint("length(trim(event_type)) > 0", name="event_type_nonempty"),
        CheckConstraint("event_version > 0", name="event_version_positive"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("length(trim(idempotency_key)) > 0", name="idempotency_nonempty"),
        Index("ix_outbox_unpublished_created", "published_at", "created_at"),
    )

    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    trace_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)


class TimelineEvent(AggregateMixin, Base):
    __tablename__ = "timeline_events"
    __table_args__ = (
        CheckConstraint("length(trim(event_type)) > 0", name="event_type_nonempty"),
        CheckConstraint("length(trim(aggregate_type)) > 0", name="aggregate_type_nonempty"),
        Index("ix_timeline_aggregate_occurred", "aggregate_type", "aggregate_id", "occurred_at"),
        Index("ix_timeline_trace_occurred", "trace_id", "occurred_at"),
    )

    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    comment_job_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    trace_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
