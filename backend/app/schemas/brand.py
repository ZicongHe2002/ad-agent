from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.domain.enums import BrandStatus

from .common import APIModel, TimestampedRead


class BrandCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    default_language: str = Field(default="zh-CN", min_length=2, max_length=16)


class BrandUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    default_language: str | None = Field(default=None, min_length=2, max_length=16)
    status: BrandStatus | None = None


class BrandRead(TimestampedRead):
    tenant_id: UUID | None
    name: str
    description: str | None
    default_language: str
    status: BrandStatus
