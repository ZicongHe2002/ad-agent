from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.domain.capabilities import PlatformCapabilities
from app.domain.enums import CapabilityName, CapabilityStatus, Platform

from .common import APIModel, TimestampedRead


class CapabilityRecordCreate(APIModel):
    platform: Platform
    capability: CapabilityName
    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    source_title: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None, max_length=2048)
    source_owner: str | None = Field(default=None, max_length=160)
    scope: dict[str, Any] = Field(default_factory=dict)
    conditions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    verified_at: datetime | None = None
    expires_at: datetime | None = None


class CapabilityRecordRead(TimestampedRead, CapabilityRecordCreate):
    tenant_id: UUID | None
    verified_by_user_id: UUID | None


class CapabilitySnapshotRead(TimestampedRead):
    tenant_id: UUID | None
    platform: Platform
    capabilities: dict[str, CapabilityStatus]
    record_ids: list[UUID]
    records_hash: str
    policy_version: str
    captured_at: datetime
    expires_at: datetime | None


class CapabilityMatrixEntry(APIModel):
    platform: Platform
    capabilities: PlatformCapabilities
    captured_at: datetime | None = None
    expires_at: datetime | None = None
    is_current: bool
