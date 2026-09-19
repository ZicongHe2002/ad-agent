from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.domain.enums import AccountKind, AuthStatus, Platform

from .common import APIModel, TimestampedRead


class BrandAccountCreate(APIModel):
    brand_id: UUID
    platform: Platform
    external_account_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=160)
    account_kind: AccountKind
    identity_profile_id: UUID
    voice_profile_id: UUID
    auto_publish_enabled: bool = False
    max_comments_per_day: int = Field(default=20, gt=0)
    credentials: dict[str, Any] | None = Field(default=None, exclude=True)


class BrandAccountRead(TimestampedRead):
    brand_id: UUID
    platform: Platform
    external_account_id: str
    display_name: str
    account_kind: AccountKind
    identity_profile_id: UUID
    voice_profile_id: UUID
    auto_publish_enabled: bool
    publisher_kill_switch: bool
    max_comments_per_day: int
    auth_status: AuthStatus
    last_auth_verified_at: datetime | None


class PlatformAuthorizationCreate(APIModel):
    tenant_id: UUID | None = None
    brand_account_id: UUID | None = None
    platform: Platform
    external_subject_id: str = Field(min_length=1, max_length=255)
    authorization_type: str = Field(default="OAUTH2", min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] | None = Field(default=None, exclude=True)


class PlatformAuthorizationRead(TimestampedRead):
    tenant_id: UUID | None
    brand_account_id: UUID | None
    platform: Platform
    external_subject_id: str
    authorization_type: str
    status: AuthStatus
    scopes: list[str]
    conditions: dict[str, Any]
    authorized_at: datetime | None
    expires_at: datetime | None
    last_verified_at: datetime | None
    revoked_at: datetime | None
