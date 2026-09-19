from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import (
    CommentJobState,
    ContentProvenance,
    DisclosureStatus,
    Platform,
    PublishMode,
    RankConfidence,
)


class PublishJob(AggregateMixin, Base):
    __tablename__ = "publish_jobs"
    __table_args__ = (
        CheckConstraint("length(trim(idempotency_key)) > 0", name="idempotency_key_nonempty"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="finish_after_start",
        ),
        CheckConstraint(
            "state IN ('READY', 'WAITING_MANUAL_PUBLISH', 'PUBLISHING', "
            "'PUBLISH_UNCERTAIN', 'READY_FOR_RETRY', 'PUBLISHED', 'FAILED', 'BLOCKED', 'SKIPPED')",
            name="publish_state_subset",
        ),
    )

    comment_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("comment_jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("comment_candidates.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    brand_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("brand_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    capability_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("capability_snapshots.id", ondelete="RESTRICT"), nullable=True
    )
    platform: Mapped[Platform] = mapped_column(enum_type(Platform), nullable=False)
    mode: Mapped[PublishMode] = mapped_column(enum_type(PublishMode), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    state: Mapped[CommentJobState] = mapped_column(
        enum_type(CommentJobState),
        nullable=False,
        default=CommentJobState.READY,
        server_default="READY",
        index=True,
    )
    state_reason: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_request_id: Mapped[str | None] = mapped_column(String(255))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    reconciliation_evidence: Mapped[dict[str, object] | None] = mapped_column(JSONType)


class PublishedComment(AggregateMixin, Base):
    __tablename__ = "published_comments"
    __table_args__ = (
        CheckConstraint("length(trim(final_text)) > 0", name="final_text_nonempty"),
        CheckConstraint(
            "chronological_rank IS NULL OR chronological_rank > 0", name="chrono_rank_positive"
        ),
        CheckConstraint("visible_rank IS NULL OR visible_rank > 0", name="visible_rank_positive"),
        Index(
            "uq_published_comments_platform_external",
            "platform",
            "external_comment_id",
            unique=True,
            postgresql_where=text("external_comment_id IS NOT NULL"),
            sqlite_where=text("external_comment_id IS NOT NULL"),
        ),
    )

    publish_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("publish_jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    creator_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("creators.id", ondelete="SET NULL"), nullable=True, index=True
    )
    brand_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("brand_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    platform: Mapped[Platform] = mapped_column(enum_type(Platform), nullable=False)
    external_comment_id: Mapped[str | None] = mapped_column(String(255))
    final_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_provenance: Mapped[ContentProvenance] = mapped_column(
        enum_type(ContentProvenance), nullable=False
    )
    disclosure_status: Mapped[DisclosureStatus] = mapped_column(
        enum_type(DisclosureStatus), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    chronological_rank: Mapped[int | None] = mapped_column(Integer)
    chronological_rank_confidence: Mapped[RankConfidence] = mapped_column(
        enum_type(RankConfidence, name="chronological_rank_confidence_enum"),
        nullable=False,
        default=RankConfidence.UNKNOWN,
        server_default="UNKNOWN",
    )
    visible_rank: Mapped[int | None] = mapped_column(Integer)
    visible_rank_confidence: Mapped[RankConfidence] = mapped_column(
        enum_type(RankConfidence, name="visible_rank_confidence_enum"),
        nullable=False,
        default=RankConfidence.UNKNOWN,
        server_default="UNKNOWN",
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rank_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
