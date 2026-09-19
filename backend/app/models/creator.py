from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import CreatorRelationship, MonitorState, Platform


class Creator(AggregateMixin, Base):
    __tablename__ = "creators"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint("priority BETWEEN 0 AND 100", name="priority_range"),
        CheckConstraint("hot_poll_interval_sec >= 5", name="hot_interval_minimum"),
        CheckConstraint(
            "normal_poll_interval_sec >= warm_poll_interval_sec",
            name="normal_not_faster_than_warm",
        ),
        CheckConstraint(
            "warm_poll_interval_sec >= hot_poll_interval_sec",
            name="warm_not_faster_than_hot",
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    relationship_type: Mapped[CreatorRelationship] = mapped_column(
        enum_type(CreatorRelationship), nullable=False
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=50, server_default="50"
    )
    normal_poll_interval_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600, server_default="600"
    )
    warm_poll_interval_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    hot_poll_interval_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )
    expected_publish_windows: Mapped[list[dict[str, object]]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    monitor_state: Mapped[MonitorState] = mapped_column(
        enum_type(MonitorState),
        nullable=False,
        default=MonitorState.ACTIVE,
        server_default="ACTIVE",
    )


class CreatorPlatformAccount(AggregateMixin, Base):
    __tablename__ = "creator_platform_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "external_creator_id", name="platform_external_creator"),
        UniqueConstraint("creator_id", "platform", name="creator_platform"),
        CheckConstraint("length(trim(external_creator_id)) > 0", name="external_creator_nonempty"),
    )

    creator_id: Mapped[UUID] = mapped_column(
        ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[Platform] = mapped_column(enum_type(Platform), nullable=False)
    external_creator_id: Mapped[str] = mapped_column(String(255), nullable=False)
    creator_url: Mapped[str | None] = mapped_column(Text)
    authorization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platform_authorizations.id", ondelete="SET NULL"), nullable=True
    )
    last_external_post_id: Mapped[str | None] = mapped_column(String(255))
    platform_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
