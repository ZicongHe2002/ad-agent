from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import DeadLetterStatus


class DeadLetterJob(AggregateMixin, Base):
    __tablename__ = "dead_letter_jobs"
    __table_args__ = (
        CheckConstraint("length(trim(source_queue)) > 0", name="source_queue_nonempty"),
        CheckConstraint("length(trim(actor_name)) > 0", name="actor_name_nonempty"),
        CheckConstraint("attempts > 0", name="attempts_positive"),
        CheckConstraint("last_failed_at >= first_failed_at", name="failure_time_order"),
    )

    source_queue: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    error: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trace_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    status: Mapped[DeadLetterStatus] = mapped_column(
        enum_type(DeadLetterStatus),
        nullable=False,
        default=DeadLetterStatus.PENDING,
        server_default="PENDING",
        index=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
