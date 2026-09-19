from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, TimestampMixin, enum_type
from app.domain.enums import AnchorType, Platform, PostStatus


class Post(AggregateMixin, Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("platform", "external_post_id", name="platform_external_post"),
        CheckConstraint("length(trim(external_post_id)) > 0", name="external_post_nonempty"),
        CheckConstraint("length(raw_payload_hash) = 64", name="payload_hash_sha256"),
        Index("ix_posts_creator_published_at", "creator_id", "published_at"),
    )

    platform: Mapped[Platform] = mapped_column(enum_type(Platform), nullable=False)
    external_post_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    creator_id: Mapped[UUID] = mapped_column(
        ForeignKey("creators.id", ondelete="CASCADE"), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[PostStatus] = mapped_column(
        enum_type(PostStatus), nullable=False, default=PostStatus.ACTIVE, server_default="ACTIVE"
    )
    raw_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_capability_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("capability_snapshots.id", ondelete="RESTRICT"), nullable=True
    )


class PostContent(TimestampMixin, Base):
    __tablename__ = "post_contents"
    __table_args__ = (
        CheckConstraint("length(content_hash) = 64", name="content_hash_sha256"),
        CheckConstraint("data_completeness BETWEEN 0 AND 1", name="completeness_range"),
        CheckConstraint("length(content_language) BETWEEN 2 AND 16", name="language_length"),
    )

    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    title: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    hashtags: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    mentions: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    ocr_text: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    visual_summary: Mapped[str | None] = mapped_column(Text)
    content_language: Mapped[str] = mapped_column(
        String(16), nullable=False, default="zh-CN", server_default="zh-CN"
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_completeness: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    model_derived_fields: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )


class PostAnchor(AggregateMixin, Base):
    __tablename__ = "post_anchors"
    __table_args__ = (
        UniqueConstraint("post_id", "anchor_type", "anchor_text", name="post_type_text"),
        CheckConstraint("length(trim(anchor_text)) > 0", name="anchor_text_nonempty"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
    )

    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    anchor_type: Mapped[AnchorType] = mapped_column(enum_type(AnchorType), nullable=False)
    anchor_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_field: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)


class OpportunityEvaluation(AggregateMixin, Base):
    __tablename__ = "opportunity_evaluations"
    __table_args__ = (
        UniqueConstraint("post_id", "campaign_id", name="post_campaign"),
        CheckConstraint("creator_value BETWEEN 0 AND 100", name="creator_value_range"),
        CheckConstraint("relevance BETWEEN 0 AND 100", name="relevance_range"),
        CheckConstraint("audience_match BETWEEN 0 AND 100", name="audience_match_range"),
        CheckConstraint("traffic_potential BETWEEN 0 AND 100", name="traffic_range"),
        CheckConstraint("post_velocity BETWEEN 0 AND 100", name="velocity_range"),
        CheckConstraint("brand_fit BETWEEN 0 AND 100", name="brand_fit_range"),
        CheckConstraint("commercial_risk BETWEEN 0 AND 100", name="commercial_risk_range"),
        CheckConstraint("platform_risk BETWEEN 0 AND 100", name="platform_risk_range"),
        CheckConstraint("final_score BETWEEN 0 AND 100", name="final_score_range"),
    )

    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    creator_value: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    relevance: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    audience_match: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    traffic_potential: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    post_velocity: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    brand_fit: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    commercial_risk: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    platform_risk: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    final_score: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
