from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import (
    CandidateStatus,
    CommentJobState,
    CommentStrategy,
    ContentProvenance,
    DisclosureStatus,
    QualityDecision,
    ReviewStatus,
    RunMode,
)


class CommentJob(AggregateMixin, Base):
    __tablename__ = "comment_jobs"
    __table_args__ = (
        UniqueConstraint(
            "post_id", "campaign_id", "brand_account_id", "intent_key", name="comment_intent"
        ),
        CheckConstraint("length(trim(intent_key)) > 0", name="intent_key_nonempty"),
        CheckConstraint("state_version >= 0", name="state_version_nonnegative"),
        CheckConstraint("regeneration_count >= 0", name="regeneration_count_nonnegative"),
        CheckConstraint("max_regenerations BETWEEN 0 AND 3", name="max_regenerations_range"),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="finish_after_start",
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brand_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("brand_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_mode: Mapped[RunMode] = mapped_column(enum_type(RunMode), nullable=False)
    intent_key: Mapped[str] = mapped_column(
        String(80), nullable=False, default="TOP_LEVEL_PRIMARY", server_default="TOP_LEVEL_PRIMARY"
    )
    state: Mapped[CommentJobState] = mapped_column(
        enum_type(CommentJobState),
        nullable=False,
        default=CommentJobState.DISCOVERED,
        server_default="DISCOVERED",
        index=True,
    )
    state_reason: Mapped[str | None] = mapped_column(Text)
    state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    selected_candidate_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("comment_candidates.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    regeneration_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_regenerations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    trace_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommentCandidate(AggregateMixin, Base):
    __tablename__ = "comment_candidates"
    __table_args__ = (
        CheckConstraint("length(trim(text)) > 0", name="text_nonempty"),
        CheckConstraint("length(trim(normalized_text)) > 0", name="normalized_text_nonempty"),
        CheckConstraint("relevance_score BETWEEN 0 AND 1", name="relevance_range"),
        CheckConstraint("commercial_score BETWEEN 0 AND 1", name="commercial_range"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
    )

    comment_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("comment_jobs.id", ondelete="CASCADE", use_alter=True), nullable=True, index=True
    )
    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brand_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("brand_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    strategy: Mapped[CommentStrategy] = mapped_column(enum_type(CommentStrategy), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_provenance: Mapped[ContentProvenance] = mapped_column(
        enum_type(ContentProvenance), nullable=False
    )
    disclosure_status: Mapped[DisclosureStatus] = mapped_column(
        enum_type(DisclosureStatus),
        nullable=False,
        default=DisclosureStatus.UNKNOWN,
        server_default="UNKNOWN",
    )
    disclosure_evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=sql_text("'{}'")
    )
    disclosure_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disclosure_resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    model_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_request_id: Mapped[str | None] = mapped_column(String(255))
    relevance_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    commercial_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    referenced_anchor_ids: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=sql_text("'[]'")
    )
    referenced_claim_ids: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=sql_text("'[]'")
    )
    generation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    uses_first_person_experience: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    implies_consumer_identity: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[CandidateStatus] = mapped_column(
        enum_type(CandidateStatus),
        nullable=False,
        default=CandidateStatus.GENERATED,
        server_default="GENERATED",
    )


class CommentQualityEvaluation(AggregateMixin, Base):
    __tablename__ = "comment_quality_evaluations"
    __table_args__ = tuple(
        CheckConstraint(f"{field} BETWEEN 0 AND 1", name=f"{field}_range")
        for field in (
            "anchor_coverage",
            "specificity",
            "fluency",
            "voice_match",
            "novelty",
            "truthfulness",
            "identity_consistency",
            "duplicate_similarity_max",
            "quality_score",
        )
    )

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("comment_candidates.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    anchor_coverage: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    specificity: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    fluency: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    voice_match: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    novelty: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    truthfulness: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    identity_consistency: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    duplicate_similarity_max: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    generic_praise_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fake_experience_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fake_identity_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unsupported_claim_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    random_typo_pattern_detected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    quality_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    decision: Mapped[QualityDecision] = mapped_column(enum_type(QualityDecision), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=sql_text("'[]'")
    )


class ReviewJob(AggregateMixin, Base):
    __tablename__ = "review_jobs"
    __table_args__ = (
        CheckConstraint(
            "status = 'PENDING' OR resolved_at IS NOT NULL",
            name="resolution_timestamp_required",
        ),
        CheckConstraint(
            "status NOT IN ('APPROVED', 'EDITED_APPROVED') OR final_text IS NOT NULL",
            name="approved_has_final_text",
        ),
        CheckConstraint(
            "edit_distance IS NULL OR edit_distance BETWEEN 0 AND 1", name="edit_distance_range"
        ),
    )

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("comment_candidates.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[ReviewStatus] = mapped_column(
        enum_type(ReviewStatus),
        nullable=False,
        default=ReviewStatus.PENDING,
        server_default="PENDING",
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_candidate_text: Mapped[str] = mapped_column(Text, nullable=False)
    final_text: Mapped[str | None] = mapped_column(Text)
    review_notes: Mapped[str | None] = mapped_column(Text)
    edit_reason: Mapped[str | None] = mapped_column(Text)
    edit_distance: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
