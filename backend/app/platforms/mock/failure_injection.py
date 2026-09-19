"""Seeded failure injection used by integration and reconciliation tests."""

from __future__ import annotations

import asyncio
import random

from pydantic import BaseModel, Field

from ..errors import (
    AuthorizationExpiredError,
    PlatformTemporaryError,
    PlatformTimeoutError,
    PublishUncertainError,
    RateLimitedError,
)


class MockFailureProfile(BaseModel):
    request_latency_ms: int = Field(default=0, ge=0, le=120_000)
    visibility_delay_ms: int = Field(default=0, ge=0, le=600_000)
    webhook_delay_ms: int = Field(default=0, ge=0, le=600_000)
    timeout_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    http_429_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    http_500_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    token_expired: bool = False
    publish_success_but_timeout_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    duplicate_webhook_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    out_of_order_event_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    seed: int = 0
    retry_after_seconds: float = Field(default=1.0, ge=0.0)


class FailureInjector:
    def __init__(self, profile: MockFailureProfile | None = None) -> None:
        self._profile = profile or MockFailureProfile()
        self._random = random.Random(self._profile.seed)

    @property
    def profile(self) -> MockFailureProfile:
        return self._profile

    def configure(self, profile: MockFailureProfile) -> MockFailureProfile:
        self._profile = profile
        self._random = random.Random(profile.seed)
        return self._profile

    def reset(self) -> None:
        self.configure(MockFailureProfile())

    def occurs(self, rate: float) -> bool:
        if rate <= 0.0:
            return False
        if rate >= 1.0:
            return True
        return self._random.random() < rate

    async def before_request(self, operation: str, *, platform: str = "MOCK") -> None:
        profile = self._profile
        if profile.request_latency_ms:
            await asyncio.sleep(profile.request_latency_ms / 1000.0)
        if profile.token_expired:
            raise AuthorizationExpiredError(
                "Injected expired authorization",
                platform=platform,
                details={"operation": operation, "injected": True},
            )
        # The order is fixed so a seeded profile is fully reproducible.
        if self.occurs(profile.http_429_rate):
            raise RateLimitedError(
                "Injected HTTP 429",
                retry_after=profile.retry_after_seconds,
                platform=platform,
                details={"operation": operation, "injected": True},
            )
        if self.occurs(profile.http_500_rate):
            raise PlatformTemporaryError(
                "Injected HTTP 500",
                platform=platform,
                details={"operation": operation, "status_code": 500, "injected": True},
            )
        if self.occurs(profile.timeout_rate):
            raise PlatformTimeoutError(
                "Injected request timeout",
                platform=platform,
                details={"operation": operation, "injected": True},
            )

    def after_publish(self, *, idempotency_key: str, platform: str = "MOCK") -> None:
        if self.occurs(self._profile.publish_success_but_timeout_rate):
            raise PublishUncertainError(
                "Mock publish succeeded but its response timed out",
                idempotency_key=idempotency_key,
                platform=platform,
                details={"injected": True, "success_before_timeout": True},
            )


__all__ = ["FailureInjector", "MockFailureProfile"]
