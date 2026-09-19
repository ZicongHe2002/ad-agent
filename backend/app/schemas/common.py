from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)


class UUIDRead(APIModel):
    id: UUID


class TimestampedRead(UUIDRead):
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_are_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


ItemT = TypeVar("ItemT")


class Page(APIModel, Generic[ItemT]):
    items: list[ItemT]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)


class ErrorDetail(APIModel):
    code: str
    message: str
    trace_id: UUID
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(APIModel):
    error: ErrorDetail


class TaskReceipt(APIModel):
    task_id: str
    trace_id: UUID
    accepted: bool = True
