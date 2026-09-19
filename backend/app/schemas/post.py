from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.domain.enums import AnchorType, Platform, PostStatus, RunMode

from .common import APIModel, TimestampedRead


class PostContentRead(APIModel):
    post_id: UUID
    title: str | None
    caption: str | None
    hashtags: list[str]
    mentions: list[str]
    ocr_text: str | None
    transcript: str | None
    visual_summary: str | None
    content_language: str
    content_hash: str
    data_completeness: float = Field(ge=0, le=1)
    model_derived_fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PostAnchorRead(TimestampedRead):
    post_id: UUID
    anchor_type: AnchorType
    anchor_text: str
    source_field: str
    confidence: float = Field(ge=0, le=1)


class OpportunityScore(APIModel):
    creator_value: float = Field(ge=0, le=100)
    relevance: float = Field(ge=0, le=100)
    audience_match: float = Field(ge=0, le=100)
    traffic_potential: float = Field(ge=0, le=100)
    post_velocity: float = Field(ge=0, le=100)
    brand_fit: float = Field(ge=0, le=100)
    commercial_risk: float = Field(ge=0, le=100)
    platform_risk: float = Field(ge=0, le=100)
    final_score: float = Field(ge=0, le=100)
    reason_codes: list[str]


class OpportunityEvaluationRead(TimestampedRead, OpportunityScore):
    post_id: UUID
    campaign_id: UUID
    prompt_version: str


class PostRead(TimestampedRead):
    platform: Platform
    external_post_id: str
    creator_id: UUID
    published_at: datetime
    detected_at: datetime
    content_updated_at: datetime | None
    status: PostStatus
    raw_payload_hash: str
    source_capability_snapshot_id: UUID | None


class PostDetail(PostRead):
    content: PostContentRead | None = None
    anchors: list[PostAnchorRead] = Field(default_factory=list)
    opportunities: list[OpportunityEvaluationRead] = Field(default_factory=list)


class ReanalyzeRequest(APIModel):
    mode: RunMode
