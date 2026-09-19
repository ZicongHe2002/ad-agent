from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, synonym

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import MetricValueType, Platform


class MetricEvent(AggregateMixin, Base):
    __tablename__ = "metric_events"
    __table_args__ = (
        CheckConstraint("length(trim(metric_name)) > 0", name="metric_name_nonempty"),
        CheckConstraint(
            "lower(metric_name) NOT LIKE '%detector%' "
            "AND lower(metric_name) NOT LIKE '%human_probability%' "
            "AND lower(metric_name) NOT LIKE '%stealth%' "
            "AND lower(metric_name) NOT LIKE '%evasion%'",
            name="forbidden_metric_names",
        ),
        Index("ix_metric_name_occurred", "metric_name", "occurred_at"),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    value_type: Mapped[MetricValueType] = mapped_column(
        enum_type(MetricValueType),
        nullable=False,
        default=MetricValueType.GAUGE,
        server_default="GAUGE",
    )
    unit: Mapped[str] = mapped_column(
        String(40), nullable=False, default="count", server_default="count"
    )
    labels: Mapped[dict[str, str]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    platform: Mapped[Platform | None] = mapped_column(enum_type(Platform))
    creator_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("creators.id", ondelete="SET NULL"), nullable=True
    )
    post_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    comment_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("comment_jobs.id", ondelete="SET NULL"), nullable=True
    )
    trace_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    observed_at = synonym("occurred_at")
