from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.enums import CampaignStatus, CommentStrategy, CreatorRelationship, RunMode

from .common import APIModel, TimestampedRead


class CampaignBase(APIModel):
    name: str = Field(min_length=1, max_length=160)
    run_mode: RunMode = RunMode.NORMAL
    start_at: datetime | None = None
    end_at: datetime | None = None
    allowed_strategies: list[CommentStrategy] = Field(default_factory=list)
    creator_relationship_allowlist: list[CreatorRelationship] = Field(default_factory=list)
    max_comments_per_day: int = Field(default=20, gt=0)
    max_comments_per_creator_per_day: int = Field(default=1, gt=0)
    human_review_required: bool = True

    @model_validator(mode="after")
    def valid_limits_and_window(self) -> CampaignBase:
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if self.max_comments_per_creator_per_day > self.max_comments_per_day:
            raise ValueError("creator daily limit must not exceed campaign daily limit")
        return self


class CampaignCreate(CampaignBase):
    brand_id: UUID


class CampaignUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    run_mode: RunMode | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    allowed_strategies: list[CommentStrategy] | None = None
    creator_relationship_allowlist: list[CreatorRelationship] | None = None
    max_comments_per_day: int | None = Field(default=None, gt=0)
    max_comments_per_creator_per_day: int | None = Field(default=None, gt=0)
    human_review_required: bool | None = None
    publisher_kill_switch: bool | None = None
    status: CampaignStatus | None = None


class CampaignRead(TimestampedRead, CampaignBase):
    brand_id: UUID
    publisher_kill_switch: bool
    status: CampaignStatus
