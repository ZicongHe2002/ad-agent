from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.domain.enums import (
    CandidateStatus,
    CommentJobState,
    CommentStrategy,
    ContentProvenance,
    DisclosureStatus,
    Platform,
    PublishMode,
    QualityDecision,
    RankConfidence,
    RiskDecision,
    RunMode,
)

from .common import APIModel, TimestampedRead


class GeneratedComment(APIModel):
    comment: str = Field(min_length=1)
    strategy: CommentStrategy
    referenced_anchor_ids: list[UUID] = Field(min_length=1)
    referenced_claim_ids: list[UUID] = Field(default_factory=list)
    relevance_score: float = Field(ge=0, le=1)
    commercial_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    generation_reason: str = Field(min_length=1)
    uses_first_person_experience: bool = False
    implies_consumer_identity: bool = False


class GeneratedCommentBatch(APIModel):
    candidates: list[GeneratedComment] = Field(min_length=1, max_length=3)
    prompt_version: str = Field(min_length=1, max_length=50)
    prompt_hash: str | None = Field(default=None, min_length=64, max_length=64)
    model_provider: str = Field(min_length=1, max_length=50)
    model_name: str = Field(min_length=1, max_length=100)
    model_request_id: str | None = Field(default=None, max_length=255)


class CommentJobRead(TimestampedRead):
    tenant_id: UUID | None
    post_id: UUID
    campaign_id: UUID
    brand_account_id: UUID
    run_mode: RunMode
    intent_key: str
    state: CommentJobState
    state_reason: str | None
    state_version: int
    selected_candidate_id: UUID | None
    regeneration_count: int
    max_regenerations: int
    trace_id: UUID
    started_at: datetime | None
    finished_at: datetime | None


class CommentCandidateRead(TimestampedRead):
    comment_job_id: UUID | None
    post_id: UUID
    campaign_id: UUID
    brand_account_id: UUID
    strategy: CommentStrategy
    text: str
    normalized_text: str
    content_provenance: ContentProvenance
    prompt_version: str
    prompt_hash: str | None
    model_provider: str
    model_name: str
    model_request_id: str | None
    relevance_score: float
    commercial_score: float
    confidence: float
    referenced_anchor_ids: list[UUID]
    referenced_claim_ids: list[UUID]
    generation_reason: str
    uses_first_person_experience: bool
    implies_consumer_identity: bool
    status: CandidateStatus


class QualityEvaluationRead(TimestampedRead):
    candidate_id: UUID
    anchor_coverage: float
    specificity: float
    fluency: float
    voice_match: float
    novelty: float
    truthfulness: float
    identity_consistency: float
    duplicate_similarity_max: float
    generic_praise_detected: bool
    fake_experience_detected: bool
    fake_identity_detected: bool
    unsupported_claim_detected: bool
    random_typo_pattern_detected: bool
    quality_score: float
    decision: QualityDecision
    reasons: list[str]


class RiskAssessment(APIModel):
    decision: RiskDecision
    risk_score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    matched_policy_categories: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)


class PublishJobRead(TimestampedRead):
    comment_job_id: UUID | None
    candidate_id: UUID
    brand_account_id: UUID
    capability_snapshot_id: UUID | None
    platform: Platform
    mode: PublishMode
    idempotency_key: str
    state: CommentJobState
    state_reason: str | None
    attempt_count: int
    next_retry_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    external_request_id: str | None
    last_error_code: str | None
    last_error_message: str | None
    reconciliation_evidence: dict[str, Any] | None


class PublishedCommentRead(TimestampedRead):
    publish_job_id: UUID
    post_id: UUID
    campaign_id: UUID | None
    creator_id: UUID | None
    brand_account_id: UUID
    platform: Platform
    external_comment_id: str | None
    final_text: str
    content_provenance: ContentProvenance
    disclosure_status: DisclosureStatus
    published_at: datetime
    chronological_rank: int | None
    chronological_rank_confidence: RankConfidence
    visible_rank: int | None
    visible_rank_confidence: RankConfidence
    removed_at: datetime | None
    rank_observed_at: datetime | None

    @field_validator("chronological_rank", "visible_rank")
    @classmethod
    def rank_is_positive(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("rank must be positive")
        return value


class RegenerateRequest(APIModel):
    reason: str = Field(min_length=1, max_length=1000)
