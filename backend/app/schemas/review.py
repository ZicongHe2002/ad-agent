from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.domain.enums import ReviewStatus

from .common import APIModel, TimestampedRead


class ReviewJobRead(TimestampedRead):
    candidate_id: UUID
    status: ReviewStatus
    assigned_to: UUID | None
    submitted_at: datetime
    expires_at: datetime | None
    resolved_at: datetime | None
    original_candidate_text: str
    final_text: str | None
    review_notes: str | None
    edit_reason: str | None
    edit_distance: float | None


class ReviewApproveRequest(APIModel):
    review_notes: str | None = Field(default=None, max_length=4000)


class ReviewEditApproveRequest(APIModel):
    final_text: str = Field(min_length=1, max_length=5000)
    edit_reason: str = Field(min_length=1, max_length=2000)
    review_notes: str | None = Field(default=None, max_length=4000)


class ReviewRejectRequest(APIModel):
    review_notes: str = Field(min_length=1, max_length=4000)
