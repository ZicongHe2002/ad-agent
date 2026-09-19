from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import CampaignStatus, RunMode


class Campaign(AggregateMixin, Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("brand_id", "name", name="campaign_brand_name"),
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint(
            "end_at IS NULL OR start_at IS NULL OR end_at > start_at", name="valid_window"
        ),
        CheckConstraint("max_comments_per_day > 0", name="daily_limit_positive"),
        CheckConstraint(
            "max_comments_per_creator_per_day > 0",
            name="creator_daily_limit_positive",
        ),
        CheckConstraint(
            "max_comments_per_creator_per_day <= max_comments_per_day",
            name="creator_limit_within_campaign_limit",
        ),
    )

    brand_id: Mapped[UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    run_mode: Mapped[RunMode] = mapped_column(
        enum_type(RunMode), nullable=False, default=RunMode.NORMAL, server_default="NORMAL"
    )
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    allowed_strategies: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    creator_relationship_allowlist: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    max_comments_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default="20"
    )
    max_comments_per_creator_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    human_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    publisher_kill_switch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[CampaignStatus] = mapped_column(
        enum_type(CampaignStatus),
        nullable=False,
        default=CampaignStatus.DRAFT,
        server_default="DRAFT",
    )
