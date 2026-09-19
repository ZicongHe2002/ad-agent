from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.clock import utc_now

from .enums import Platform

EVENT_TYPES = frozenset(
    {
        "creator.poll.requested",
        "creator.poll.started",
        "creator.poll.completed",
        "creator.poll.failed",
        "post.detected",
        "post.fetch.started",
        "post.fetch.completed",
        "post.normalized",
        "post.analysis.started",
        "post.analysis.completed",
        "post.skipped",
        "comment.generation.started",
        "comment.generated",
        "comment.quality.started",
        "comment.quality.completed",
        "risk.check.started",
        "risk.check.completed",
        "review.requested",
        "review.completed",
        "comment.publish.requested",
        "comment.reconcile.requested",
        "comment.publish.started",
        "comment.publish.uncertain",
        "comment.published",
        "comment.publish.failed",
        "comment.reconciled",
    }
)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    event_version: int = Field(default=1, ge=1)
    occurred_at: datetime = Field(default_factory=utc_now)
    observed_at: datetime = Field(default_factory=utc_now)
    platform: Platform | None = None
    creator_id: UUID | None = None
    post_id: UUID | None = None
    campaign_id: UUID | None = None
    trace_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID = Field(default_factory=uuid4)
    idempotency_key: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at", "observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("event timestamps must be timezone-aware")
        return value
