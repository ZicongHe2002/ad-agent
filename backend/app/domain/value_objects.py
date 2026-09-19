from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import CapabilityStatus, Platform, PublishMode


class CapabilityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_title: str = Field(min_length=1, max_length=255)
    source_owner: str = Field(min_length=1, max_length=160)
    source_url: str | None = Field(default=None, max_length=2048)
    verified_at: datetime
    expires_at: datetime | None = None
    verified_by_user_id: UUID | None = None

    @field_validator("verified_at", "expires_at")
    @classmethod
    def timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("capability evidence timestamps must be timezone-aware")
        return value


class AuthorizationScope(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    scopes: list[str] = Field(default_factory=list)
    account_types: list[str] = Field(default_factory=list)
    target_content_types: list[str] = Field(default_factory=list)
    authorization_required: bool = True


class PublishRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    platform: Platform
    mode: PublishMode
    capability_status: CapabilityStatus
    permitted: bool
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)
