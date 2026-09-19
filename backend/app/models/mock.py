from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TimestampMixin


class MockPlatformState(TimestampMixin, Base):
    """Shared configuration for the development-only Mock Platform."""

    __tablename__ = "mock_platform_state"

    key: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    capabilities: Mapped[dict[str, str]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    policy: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    failure_profile: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )


class MockCreatorRecord(TimestampMixin, Base):
    __tablename__ = "mock_creators"

    external_creator_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    platform_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )


class MockPostRecord(TimestampMixin, Base):
    __tablename__ = "mock_posts"

    external_post_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    external_creator_id: Mapped[str] = mapped_column(
        ForeignKey("mock_creators.external_creator_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    hashtags: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    mentions: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    media_urls: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    raw_payload: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )


class MockCommentRecord(TimestampMixin, Base):
    __tablename__ = "mock_comments"

    external_comment_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    external_post_id: Mapped[str] = mapped_column(
        ForeignKey("mock_posts.external_post_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body: Mapped[str] = mapped_column("text", Text, nullable=False)
    platform_created_at: Mapped[datetime] = mapped_column(
        "platform_created_at", DateTime(timezone=True), nullable=False, index=True
    )
    author_external_id: Mapped[str | None] = mapped_column(String(255))
    parent_comment_id: Mapped[str | None] = mapped_column(String(255), index=True)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    author_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    visible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    raw_payload: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    account_id: Mapped[str | None] = mapped_column(String(255))
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
