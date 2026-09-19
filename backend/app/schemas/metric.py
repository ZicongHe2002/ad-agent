from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.domain.enums import MetricValueType, Platform

from .common import APIModel, TimestampedRead


class MetricEventCreate(APIModel):
    metric_name: str = Field(min_length=1, max_length=160)
    value: float
    value_type: MetricValueType = MetricValueType.GAUGE
    unit: str = Field(default="count", min_length=1, max_length=40)
    labels: dict[str, str] = Field(default_factory=dict)
    platform: Platform | None = None
    creator_id: UUID | None = None
    post_id: UUID | None = None
    campaign_id: UUID | None = None
    comment_job_id: UUID | None = None
    trace_id: UUID | None = None
    occurred_at: datetime


class MetricEventRead(TimestampedRead, MetricEventCreate):
    tenant_id: UUID | None


class TimelineEventRead(TimestampedRead):
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    comment_job_id: UUID | None
    trace_id: UUID
    payload: dict[str, Any]
    occurred_at: datetime


class LatencySummary(APIModel):
    count: int = Field(ge=0)
    p50: float | None
    p90: float | None
    p95: float | None
    p99: float | None


class RankingSummary(APIModel):
    samples: int = Field(ge=0)
    measured: int = Field(ge=0)
    measurement_coverage: float = Field(ge=0, le=1)
    first_comment_success_rate: float = Field(ge=0, le=1)
    top5_success_rate: float = Field(ge=0, le=1)
