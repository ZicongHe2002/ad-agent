from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.domain.enums import CapabilityStatus

from .common import APIModel


class MockCreatorCreate(APIModel):
    external_creator_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MockPostCreate(APIModel):
    external_creator_id: str = Field(min_length=1, max_length=255)
    external_post_id: str = Field(min_length=1, max_length=255)
    published_at: datetime
    title: str | None = None
    caption: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class MockCommentCreate(APIModel):
    text: str = Field(min_length=1, max_length=10_000)
    external_account_id: str = Field(min_length=1, max_length=255)
    idempotency_key: str | None = Field(default=None, max_length=255)


class MockCapabilityUpdate(APIModel):
    capabilities: dict[str, CapabilityStatus]


class MockFailureProfileUpdate(APIModel):
    request_latency_ms: int = Field(default=0, ge=0, le=60_000)
    visibility_delay_ms: int = Field(default=0, ge=0, le=60_000)
    webhook_delay_ms: int = Field(default=0, ge=0, le=60_000)
    timeout_rate: float = Field(default=0, ge=0, le=1)
    http_429_rate: float = Field(default=0, ge=0, le=1)
    http_500_rate: float = Field(default=0, ge=0, le=1)
    token_expired: bool = False
    publish_success_but_timeout_rate: float = Field(default=0, ge=0, le=1)
    duplicate_webhook_rate: float = Field(default=0, ge=0, le=1)
    out_of_order_event_rate: float = Field(default=0, ge=0, le=1)
