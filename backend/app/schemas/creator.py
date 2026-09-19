from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.enums import CreatorRelationship, MonitorState, Platform

from .common import APIModel, TimestampedRead


class CreatorPlatformAccountCreate(APIModel):
    platform: Platform
    external_creator_id: str = Field(min_length=1, max_length=255)
    creator_url: str | None = None
    authorization_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatorPlatformAccountRead(TimestampedRead):
    creator_id: UUID
    platform: Platform
    external_creator_id: str
    creator_url: str | None
    authorization_id: UUID | None
    last_external_post_id: str | None
    metadata: dict[str, Any] = Field(validation_alias="platform_metadata")


class CreatorCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=100)
    relationship_type: CreatorRelationship
    priority: int = Field(default=50, ge=0, le=100)
    normal_poll_interval_sec: int = Field(default=600, ge=5, le=3600)
    warm_poll_interval_sec: int = Field(default=60, ge=5, le=3600)
    hot_poll_interval_sec: int = Field(default=10, ge=5, le=3600)
    expected_publish_windows: list[dict[str, Any]] = Field(default_factory=list)
    platform_accounts: list[CreatorPlatformAccountCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def polling_intervals_are_ordered(self) -> CreatorCreate:
        if not (
            self.normal_poll_interval_sec
            >= self.warm_poll_interval_sec
            >= self.hot_poll_interval_sec
        ):
            raise ValueError("poll intervals must satisfy normal >= warm >= hot")
        return self


class CreatorUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    relationship_type: CreatorRelationship | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    normal_poll_interval_sec: int | None = Field(default=None, ge=5, le=3600)
    warm_poll_interval_sec: int | None = Field(default=None, ge=5, le=3600)
    hot_poll_interval_sec: int | None = Field(default=None, ge=5, le=3600)
    expected_publish_windows: list[dict[str, Any]] | None = None
    monitor_state: MonitorState | None = None


class CreatorRead(TimestampedRead):
    tenant_id: UUID | None
    name: str
    category: str
    relationship_type: CreatorRelationship
    priority: int
    normal_poll_interval_sec: int
    warm_poll_interval_sec: int
    hot_poll_interval_sec: int
    expected_publish_windows: list[dict[str, Any]]
    last_checked_at: datetime | None
    last_post_at: datetime | None
    monitor_state: MonitorState
