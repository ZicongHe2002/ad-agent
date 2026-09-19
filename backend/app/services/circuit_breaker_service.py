from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

CIRCUIT_ACQUIRE_SCRIPT = """
local state_key = KEYS[1]
local probe_key = KEYS[2]
local now = tonumber(ARGV[1])
local recovery_timeout = tonumber(ARGV[2])

local state = redis.call('HGET', state_key, 'state')
if state == false or state == 'CLOSED' then
  return {1, 'CLOSED', '0'}
end

local opened_at = tonumber(redis.call('HGET', state_key, 'opened_at') or now)
local elapsed = math.max(0, now - opened_at)
if (state == 'OPEN' and elapsed >= recovery_timeout) or state == 'HALF_OPEN' then
  local acquired = redis.call('SET', probe_key, '1', 'NX', 'EX', math.ceil(recovery_timeout))
  if acquired then
    redis.call('HSET', state_key, 'state', 'HALF_OPEN')
    return {1, 'HALF_OPEN', '0'}
  end
  local probe_ttl = redis.call('TTL', probe_key)
  return {0, 'HALF_OPEN', tostring(math.max(1, probe_ttl))}
end

return {0, state, tostring(math.max(1, recovery_timeout - elapsed))}
"""


CIRCUIT_FAILURE_SCRIPT = """
local state_key = KEYS[1]
local probe_key = KEYS[2]
local now = tonumber(ARGV[1])
local threshold = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

local state = redis.call('HGET', state_key, 'state') or 'CLOSED'
local failures = redis.call('HINCRBY', state_key, 'failures', 1)
if state == 'HALF_OPEN' or failures >= threshold then
  state = 'OPEN'
  redis.call('HSET', state_key, 'state', state, 'opened_at', tostring(now))
  redis.call('DEL', probe_key)
else
  redis.call('HSET', state_key, 'state', state)
end
redis.call('EXPIRE', state_key, ttl)
return {state, failures}
"""


CIRCUIT_SUCCESS_SCRIPT = """
redis.call('DEL', KEYS[1], KEYS[2])
return 1
"""


@dataclass(frozen=True, slots=True)
class CircuitDecision:
    allowed: bool
    state: str
    retry_after_seconds: int = 0


class RedisCircuitBreaker:
    """Shared circuit breaker scoped to one platform operation."""

    def __init__(
        self,
        redis: Any,
        platform: str,
        operation: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 30,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if recovery_timeout_seconds < 1:
            raise ValueError("recovery_timeout_seconds must be positive")
        scope = f"{platform}:{operation}"
        self.redis = redis
        self.state_key = f"circuit:{scope}"
        self.probe_key = f"circuit_probe:{scope}"
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds

    async def acquire(self, *, now: float | None = None) -> CircuitDecision:
        timestamp = time.time() if now is None else now
        raw = await self.redis.eval(
            CIRCUIT_ACQUIRE_SCRIPT,
            2,
            self.state_key,
            self.probe_key,
            timestamp,
            self.recovery_timeout_seconds,
        )
        state = _decode(raw[1])
        retry_after = float(_decode(raw[2]))
        allowed = int(raw[0]) == 1
        return CircuitDecision(
            allowed=allowed,
            state=state,
            retry_after_seconds=0 if allowed else max(1, math.ceil(retry_after)),
        )

    async def record_failure(self, *, now: float | None = None) -> str:
        timestamp = time.time() if now is None else now
        raw = await self.redis.eval(
            CIRCUIT_FAILURE_SCRIPT,
            2,
            self.state_key,
            self.probe_key,
            timestamp,
            self.failure_threshold,
            max(300, self.recovery_timeout_seconds * 10),
        )
        return _decode(raw[0])

    async def record_success(self) -> None:
        await self.redis.eval(
            CIRCUIT_SUCCESS_SCRIPT,
            2,
            self.state_key,
            self.probe_key,
        )


def _decode(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
