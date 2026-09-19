from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

SCHEDULABLE_CAPABILITIES = {"SUPPORTED", "CONDITIONAL", "AUTH_REQUIRED"}


PLATFORM_QUOTA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_per_second = tonumber(ARGV[3])
local amount = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local state = redis.call('HMGET', key, 'tokens', 'updated_at')
local tokens = tonumber(state[1])
local updated_at = tonumber(state[2])
if tokens == nil then
  tokens = capacity
  updated_at = now
end

local elapsed = math.max(0, now - updated_at)
tokens = math.min(capacity, tokens + elapsed * refill_per_second)

local allowed = 0
local retry_after = 0
if tokens >= amount then
  tokens = tokens - amount
  allowed = 1
elseif refill_per_second > 0 then
  retry_after = (amount - tokens) / refill_per_second
else
  retry_after = ttl
end

redis.call('HSET', key, 'tokens', tostring(tokens), 'updated_at', tostring(now))
redis.call('EXPIRE', key, ttl)
return {allowed, tostring(tokens), tostring(retry_after)}
"""


RELEASE_POLL_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class PollingContext:
    creator_platform_account_id: str
    normal_interval_sec: int = 600
    warm_interval_sec: int = 60
    hot_interval_sec: int = 10
    priority: int = 50
    in_expected_publish_window: bool = False
    in_high_probability_window: bool = False
    recent_activity_score: float = 0.0
    failure_count: int = 0
    platform_rate_limit_pressure: float = 0.0
    capability_status: str = "UNKNOWN"
    auth_invalid: bool = False
    monitor_paused: bool = False
    current_hour: str | None = None


def deterministic_jitter(entity_id: str, current_hour: str | None = None) -> float:
    hour = current_hour or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    digest = hashlib.sha256(f"{entity_id}:{hour}".encode()).digest()
    bucket = int.from_bytes(digest[:4], "big") % 3000
    return 0.85 + bucket / 10_000


def next_poll_interval(ctx: PollingContext) -> int:
    if ctx.monitor_paused:
        return 3600
    if ctx.capability_status not in SCHEDULABLE_CAPABILITIES:
        return 3600
    if ctx.auth_invalid:
        return 1800

    base = ctx.normal_interval_sec
    if ctx.in_expected_publish_window:
        base = ctx.warm_interval_sec
    if ctx.priority >= 90 and ctx.in_high_probability_window:
        base = ctx.hot_interval_sec
    if ctx.recent_activity_score >= 0.8:
        base = min(base, ctx.warm_interval_sec)
    if ctx.failure_count > 0:
        exponent = min(ctx.failure_count, 16)
        base = max(base, min(3600, (2**exponent) * 15))
    if ctx.platform_rate_limit_pressure >= 0.8:
        base = int(base * 2.5)
    return max(
        5,
        min(
            3600,
            int(base * deterministic_jitter(ctx.creator_platform_account_id, ctx.current_hour)),
        ),
    )


def polling_window_flags(
    windows: Sequence[Mapping[str, object]],
    *,
    now: datetime | None = None,
) -> tuple[bool, bool]:
    """Evaluate documented expected-publish windows without guessing a timezone.

    A window accepts ``start``/``end`` as ``HH:MM`` (or
    ``start_hour``/``end_hour``), optional ISO weekday numbers in ``days``, and
    an optional ``timezone_offset_minutes``.  Unknown shapes fail closed.
    """

    current_utc = now or datetime.now(timezone.utc)
    if current_utc.tzinfo is None:
        current_utc = current_utc.replace(tzinfo=timezone.utc)
    in_window = False
    high_probability = False
    for window in windows:
        try:
            raw_offset = window.get("timezone_offset_minutes", 0)
            if not isinstance(raw_offset, (int, float, str)):
                continue
            offset = int(raw_offset)
            local_now = current_utc.astimezone(timezone.utc) + timedelta(minutes=offset)
            days = window.get("days", window.get("days_of_week"))
            if isinstance(days, Sequence) and not isinstance(days, (str, bytes)):
                allowed_days = {int(value) for value in days}
                # The documented shape uses ISO weekdays (1=Monday).  Accept the
                # common zero-based variant only when a zero is present, so an
                # otherwise ambiguous value such as ``1`` does not match two days.
                current_day = (
                    local_now.weekday() if 0 in allowed_days else local_now.isoweekday()
                )
                if current_day not in allowed_days:
                    continue
            start = _clock_minutes(window.get("start", window.get("start_hour")))
            end = _clock_minutes(window.get("end", window.get("end_hour")))
            if start is None or end is None:
                continue
            minute = local_now.hour * 60 + local_now.minute
            active = start <= minute < end if start <= end else minute >= start or minute < end
            if not active:
                continue
            in_window = True
            raw_probability = window.get("probability", window.get("confidence", 0.0))
            if not isinstance(raw_probability, (int, float, str)):
                raw_probability = 0.0
            probability = float(raw_probability)
            high_probability = high_probability or bool(window.get("high_probability", False))
            high_probability = high_probability or probability >= 0.8
        except (TypeError, ValueError):
            continue
    return in_window, high_probability


def recent_activity_score(
    published_at: Sequence[datetime],
    *,
    now: datetime | None = None,
) -> float:
    if not published_at:
        return 0.0
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    values = [
        item if item.tzinfo is not None else item.replace(tzinfo=timezone.utc)
        for item in published_at
    ]
    latest = max(values)
    age_seconds = max(0.0, (current - latest).total_seconds())
    if age_seconds <= 3600:
        return 1.0
    if age_seconds <= 6 * 3600:
        return 0.85
    if age_seconds <= 24 * 3600:
        return 0.6
    if age_seconds <= 72 * 3600:
        return 0.3
    return 0.0


def _clock_minutes(value: object) -> int | None:
    if isinstance(value, int | float):
        hour = float(value)
        if 0 <= hour <= 24:
            return min(1439, int(hour * 60))
        return None
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":", 1)
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) == 2 else 0
    except ValueError:
        return None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return hour * 60 + minute


class InMemoryTokenBucket:
    """Deterministic test token bucket; production uses the Redis Lua equivalent."""

    def __init__(self, capacity: float, refill_per_second: float) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.tokens = capacity
        self.updated_at = 0.0

    def acquire(self, now: float, amount: float = 1.0) -> bool:
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.updated_at = now
        if self.tokens < amount:
            return False
        self.tokens -= amount
        return True


@dataclass(frozen=True, slots=True)
class TokenBucketDecision:
    allowed: bool
    remaining_tokens: float
    retry_after_seconds: int


class RedisPlatformTokenBucket:
    """Atomic, platform-scoped quota shared by every polling worker.

    The key intentionally contains only the platform, never an account.  A caller
    therefore cannot evade the platform quota by rotating creator accounts.
    """

    def __init__(
        self,
        redis: Any,
        platform: str,
        *,
        capacity: float = 10.0,
        refill_per_second: float = 1.0,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_per_second < 0:
            raise ValueError("refill_per_second cannot be negative")
        self.redis = redis
        self.key = f"poll_token_bucket:{platform}"
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)

    async def acquire(
        self,
        *,
        now: float | None = None,
        amount: float = 1.0,
    ) -> TokenBucketDecision:
        if amount <= 0 or amount > self.capacity:
            raise ValueError("amount must be positive and no larger than capacity")
        timestamp = time.time() if now is None else now
        refill_window = (
            self.capacity / self.refill_per_second if self.refill_per_second else 3600.0
        )
        ttl_seconds = max(60, math.ceil(refill_window * 2))
        raw = await self.redis.eval(
            PLATFORM_QUOTA_SCRIPT,
            1,
            self.key,
            timestamp,
            self.capacity,
            self.refill_per_second,
            amount,
            ttl_seconds,
        )
        allowed = int(raw[0]) == 1
        remaining = float(_decode_redis_value(raw[1]))
        retry_after = float(_decode_redis_value(raw[2]))
        return TokenBucketDecision(
            allowed=allowed,
            remaining_tokens=max(0.0, remaining),
            retry_after_seconds=0 if allowed else max(1, math.ceil(retry_after)),
        )


class RedisPollLock:
    """Ownership-safe Redis lock for a creator platform account poll."""

    def __init__(
        self,
        redis: Any,
        creator_platform_account_id: str,
        *,
        expected_request_timeout_seconds: float = 30.0,
    ) -> None:
        self.redis = redis
        self.key = f"poll_lock:{creator_platform_account_id}"
        self.ttl_seconds = max(30, math.ceil(expected_request_timeout_seconds * 2))
        self.token = uuid4().hex
        self.acquired = False

    async def acquire(self) -> bool:
        self.acquired = bool(
            await self.redis.set(
                self.key,
                self.token,
                nx=True,
                ex=self.ttl_seconds,
            )
        )
        return self.acquired

    async def release(self) -> bool:
        if not self.acquired:
            return False
        released = await self.redis.eval(RELEASE_POLL_LOCK_SCRIPT, 1, self.key, self.token)
        self.acquired = False
        return bool(released)


class RedisPollFailureTracker:
    """Stores consecutive failures long enough to influence adaptive backoff."""

    def __init__(self, redis: Any, creator_platform_account_id: str) -> None:
        self.redis = redis
        self.key = f"poll_failure_count:{creator_platform_account_id}"

    async def current(self) -> int:
        value = await self.redis.get(self.key)
        return max(0, int(_decode_redis_value(value))) if value is not None else 0

    async def record_failure(self) -> int:
        value = int(await self.redis.incr(self.key))
        await self.redis.expire(self.key, 86_400)
        return value

    async def reset(self) -> None:
        await self.redis.delete(self.key)


class RedisPlatformRatePressure:
    """Short-lived platform pressure signal consumed by adaptive polling."""

    def __init__(self, redis: Any, platform: str) -> None:
        self.redis = redis
        self.key = f"poll_rate_pressure:{platform}"

    async def current(self) -> float:
        value = await self.redis.get(self.key)
        if value is None:
            return 0.0
        try:
            return max(0.0, min(1.0, float(_decode_redis_value(value))))
        except ValueError:
            return 0.0

    async def record_limited(self, *, ttl_seconds: int = 300) -> None:
        await self.redis.set(self.key, "1", ex=ttl_seconds)

    async def reset(self) -> None:
        await self.redis.delete(self.key)


def _decode_redis_value(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
