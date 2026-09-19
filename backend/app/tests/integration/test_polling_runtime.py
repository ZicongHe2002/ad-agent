from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.domain.enums import CreatorRelationship, MonitorState, Platform
from app.models import Creator, CreatorPlatformAccount, TimelineEvent
from app.platforms.mock.failure_injection import MockFailureProfile
from app.platforms.runtime import mock_service
from app.services.circuit_breaker_service import (
    CIRCUIT_ACQUIRE_SCRIPT,
    CIRCUIT_FAILURE_SCRIPT,
    CIRCUIT_SUCCESS_SCRIPT,
    RedisCircuitBreaker,
)
from app.services.discovery_service import _validated_source_url
from app.services.monitor_service import (
    PLATFORM_QUOTA_SCRIPT,
    RELEASE_POLL_LOCK_SCRIPT,
    RedisPlatformTokenBucket,
    RedisPollLock,
)
from app.workers.health import heartbeat_status, write_heartbeat
from app.workers.monitor_actors import run_creator_platform_account_poll
from app.workers.scheduler import (
    CLAIM_DUE_SCRIPT,
    REQUEUE_EXPIRED_SCRIPT,
    RedisPollingSchedule,
    _dispatch_platform,
)


class _Pipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.operations: list[Callable[[], None]] = []

    def zrem(self, key: str, member: str) -> _Pipeline:
        self.operations.append(lambda: self.redis.sorted_sets.setdefault(key, {}).pop(member, None))
        return self

    def zadd(self, key: str, values: dict[str, float]) -> _Pipeline:
        self.operations.append(lambda: self.redis.sorted_sets.setdefault(key, {}).update(values))
        return self

    async def execute(self) -> list[None]:
        for operation in self.operations:
            operation()
        return [None] * len(self.operations)


class FakeRedis:
    """Small async Redis model covering the scripts used by the polling runtime."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.hashes: dict[str, dict[str, Any]] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.closed = False

    async def set(
        self,
        key: str,
        value: Any,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key: str) -> Any:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        return int(existed)

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value

    async def expire(self, key: str, seconds: int) -> bool:
        del seconds
        return key in self.values or key in self.hashes

    async def mget(self, keys: list[str]) -> list[Any]:
        return [self.values.get(key) for key in keys]

    async def zadd(self, key: str, values: dict[str, float]) -> int:
        target = self.sorted_sets.setdefault(key, {})
        before = len(target)
        target.update(values)
        return len(target) - before

    async def zrem(self, key: str, member: str) -> int:
        target = self.sorted_sets.setdefault(key, {})
        existed = member in target
        target.pop(member, None)
        return int(existed)

    async def zscore(self, key: str, member: str) -> float | None:
        return self.sorted_sets.setdefault(key, {}).get(member)

    def pipeline(self, *, transaction: bool = True) -> _Pipeline:
        assert transaction
        return _Pipeline(self)

    async def eval(self, script: str, number_of_keys: int, *args: Any) -> list[Any] | int:
        del number_of_keys
        if script == RELEASE_POLL_LOCK_SCRIPT:
            key, token = str(args[0]), str(args[1])
            if self.values.get(key) != token:
                return 0
            self.values.pop(key, None)
            return 1
        if script == PLATFORM_QUOTA_SCRIPT:
            key = str(args[0])
            now, capacity, refill, amount = map(float, args[1:5])
            state = self.hashes.get(key, {"tokens": capacity, "updated_at": now})
            elapsed = max(0.0, now - state["updated_at"])
            tokens = min(capacity, state["tokens"] + elapsed * refill)
            allowed = tokens >= amount
            if allowed:
                tokens -= amount
                retry_after = 0.0
            else:
                retry_after = (amount - tokens) / refill if refill else float(args[5])
            self.hashes[key] = {"tokens": tokens, "updated_at": now}
            return [int(allowed), str(tokens).encode(), str(retry_after).encode()]
        if script == CIRCUIT_ACQUIRE_SCRIPT:
            state_key, probe_key = str(args[0]), str(args[1])
            now, recovery_timeout = float(args[2]), float(args[3])
            state_data = self.hashes.get(state_key, {})
            state = str(state_data.get("state", "CLOSED"))
            if state == "CLOSED":
                return [1, b"CLOSED", b"0"]
            opened_at = float(state_data.get("opened_at", now))
            elapsed = max(0.0, now - opened_at)
            recovery_due = state == "OPEN" and elapsed >= recovery_timeout
            if (recovery_due or state == "HALF_OPEN") and probe_key not in self.values:
                self.values[probe_key] = "1"
                state_data["state"] = "HALF_OPEN"
                return [1, b"HALF_OPEN", b"0"]
            return [
                0,
                state.encode(),
                str(max(1.0, recovery_timeout - elapsed)).encode(),
            ]
        if script == CIRCUIT_FAILURE_SCRIPT:
            state_key, probe_key = str(args[0]), str(args[1])
            now, threshold = float(args[2]), int(args[3])
            state_data = self.hashes.setdefault(state_key, {})
            state = str(state_data.get("state", "CLOSED"))
            failures = int(state_data.get("failures", 0)) + 1
            state_data["failures"] = failures
            if state == "HALF_OPEN" or failures >= threshold:
                state = "OPEN"
                state_data["opened_at"] = now
                self.values.pop(probe_key, None)
            state_data["state"] = state
            return [state.encode(), failures]
        if script == CIRCUIT_SUCCESS_SCRIPT:
            state_key, probe_key = str(args[0]), str(args[1])
            self.hashes.pop(state_key, None)
            self.values.pop(probe_key, None)
            return 1
        if script == CLAIM_DUE_SCRIPT:
            schedule_key, lease_key = str(args[0]), str(args[1])
            now, lease_until, limit = float(args[2]), float(args[3]), int(args[4])
            schedule = self.sorted_sets.setdefault(schedule_key, {})
            due = [
                member
                for member, _score in sorted(schedule.items(), key=lambda item: item[1])
                if _score <= now
            ][:limit]
            for member in due:
                schedule.pop(member, None)
                self.sorted_sets.setdefault(lease_key, {})[member] = lease_until
            return [member.encode() for member in due]
        if script == REQUEUE_EXPIRED_SCRIPT:
            lease_key, schedule_key = str(args[0]), str(args[1])
            now, limit = float(args[2]), int(args[3])
            leases = self.sorted_sets.setdefault(lease_key, {})
            expired = [
                member
                for member, _score in sorted(leases.items(), key=lambda item: item[1])
                if _score <= now
            ][:limit]
            for member in expired:
                leases.pop(member, None)
                self.sorted_sets.setdefault(schedule_key, {})[member] = now
            return [member.encode() for member in expired]
        raise AssertionError("unexpected Lua script")

    async def close(self) -> None:
        self.closed = True


async def _seed_creator(factory, *, interval: int = 5) -> tuple[UUID, UUID, str]:
    external_creator_id = f"poll-creator-{uuid4()}"
    await mock_service.create_creator("Polling test", external_creator_id=external_creator_id)
    async with factory() as session, session.begin():
        creator = Creator(
            tenant_id=None,
            name="Polling test",
            category="test",
            relationship_type=CreatorRelationship.PARTNER_CREATOR,
            priority=50,
            normal_poll_interval_sec=interval,
            warm_poll_interval_sec=interval,
            hot_poll_interval_sec=interval,
            monitor_state=MonitorState.ACTIVE,
        )
        session.add(creator)
        await session.flush()
        account = CreatorPlatformAccount(
            creator_id=creator.id,
            platform=Platform.MOCK,
            external_creator_id=external_creator_id,
        )
        session.add(account)
        await session.flush()
        return creator.id, account.id, external_creator_id


async def test_schedule_claim_is_atomic_and_completion_is_explicit() -> None:
    redis = FakeRedis()
    account_id = str(uuid4())
    first = RedisPollingSchedule(redis, Platform.MOCK.value)
    second = RedisPollingSchedule(redis, Platform.MOCK.value)
    await first.schedule(account_id, 10)

    claimed = await asyncio.gather(
        first.claim_due(now=10),
        second.claim_due(now=10),
    )
    assert sum(len(items) for items in claimed) == 1
    assert await redis.zscore(first.schedule_key, account_id) is None
    assert await redis.zscore(first.lease_key, account_id) is not None

    await first.complete(account_id, 20)
    assert await redis.zscore(first.lease_key, account_id) is None
    assert await redis.zscore(first.schedule_key, account_id) == 20


async def test_lock_and_platform_bucket_are_shared_across_accounts() -> None:
    redis = FakeRedis()
    first_lock = RedisPollLock(redis, "account-a", expected_request_timeout_seconds=8)
    second_lock = RedisPollLock(redis, "account-a", expected_request_timeout_seconds=8)
    assert first_lock.ttl_seconds == 30
    assert await first_lock.acquire()
    assert not await second_lock.acquire()
    assert await first_lock.release()
    assert await second_lock.acquire()

    account_a_bucket = RedisPlatformTokenBucket(
        redis, Platform.MOCK.value, capacity=1, refill_per_second=0.5
    )
    account_b_bucket = RedisPlatformTokenBucket(
        redis, Platform.MOCK.value, capacity=1, refill_per_second=0.5
    )
    assert (await account_a_bucket.acquire(now=100)).allowed
    delayed = await account_b_bucket.acquire(now=100)
    assert not delayed.allowed
    assert delayed.retry_after_seconds == 2
    assert (await account_b_bucket.acquire(now=102)).allowed


async def test_platform_operation_circuit_opens_and_allows_one_recovery_probe() -> None:
    redis = FakeRedis()
    circuit = RedisCircuitBreaker(
        redis,
        Platform.MOCK.value,
        "get_latest_posts",
        failure_threshold=2,
        recovery_timeout_seconds=30,
    )
    assert (await circuit.acquire(now=100)).allowed
    assert await circuit.record_failure(now=100) == "CLOSED"
    assert await circuit.record_failure(now=101) == "OPEN"
    blocked = await circuit.acquire(now=110)
    assert not blocked.allowed
    assert blocked.retry_after_seconds == 21

    probe = await circuit.acquire(now=131)
    duplicate_probe = await circuit.acquire(now=131)
    assert probe.allowed and probe.state == "HALF_OPEN"
    assert not duplicate_probe.allowed
    await circuit.record_success()
    assert (await circuit.acquire(now=132)).allowed


def test_source_url_validation_never_synthesizes_or_accepts_unsafe_schemes() -> None:
    assert _validated_source_url(None, "javascript:alert(1)", "post/123") is None
    assert (
        _validated_source_url(" ", "https://social.example/posts/123 ")
        == "https://social.example/posts/123"
    )


async def test_scheduler_dispatches_account_id_and_keeps_lease_until_worker(
    clean_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _creator_id, account_id, _external = await _seed_creator(clean_database)
    redis = FakeRedis()
    schedule = RedisPollingSchedule(redis, Platform.MOCK.value)
    await schedule.schedule(str(account_id), 0)
    dispatched: list[tuple[str, str]] = []

    from app.workers import monitor_actors

    monkeypatch.setattr(
        monitor_actors.poll_creator_account,
        "send",
        lambda target_id, platform: dispatched.append((target_id, platform)),
    )
    assert await _dispatch_platform(redis, Platform.MOCK) == 1
    assert dispatched == [(str(account_id), Platform.MOCK.value)]
    assert await redis.zscore(schedule.schedule_key, str(account_id)) is None
    assert await redis.zscore(schedule.lease_key, str(account_id)) is not None


async def test_worker_completes_lease_after_success_and_writes_timeline(clean_database) -> None:
    _creator_id, account_id, external_creator_id = await _seed_creator(clean_database)
    await mock_service.create_post(
        external_creator_id,
        external_post_id=f"poll-post-{uuid4()}",
        caption="new post",
    )
    redis = FakeRedis()
    schedule = RedisPollingSchedule(redis, Platform.MOCK.value)
    redis.sorted_sets[schedule.lease_key] = {str(account_id): time.time() + 60}

    result = await run_creator_platform_account_poll(
        str(account_id), Platform.MOCK.value, redis=redis
    )
    assert result["inserted"] == 1
    assert result["failure_count"] == 0
    assert await redis.zscore(schedule.lease_key, str(account_id)) is None
    assert await redis.zscore(schedule.schedule_key, str(account_id)) is not None

    async with clean_database() as session:
        events = list(
            await session.scalars(
                select(TimelineEvent)
                .where(TimelineEvent.aggregate_id == account_id)
                .order_by(TimelineEvent.occurred_at, TimelineEvent.created_at)
            )
        )
    assert [event.event_type for event in events] == [
        "creator.poll.started",
        "creator.poll.completed",
    ]


async def test_failures_increment_backoff_and_write_failed_timeline(clean_database) -> None:
    _creator_id, account_id, _external = await _seed_creator(clean_database)
    await mock_service.configure_failure_profile(MockFailureProfile(http_500_rate=1.0))
    redis = FakeRedis()

    first = await run_creator_platform_account_poll(
        str(account_id), Platform.MOCK.value, redis=redis
    )
    second = await run_creator_platform_account_poll(
        str(account_id), Platform.MOCK.value, redis=redis
    )
    assert first["failure_count"] == 1
    assert second["failure_count"] == 2
    assert second["next_poll_in_seconds"] > first["next_poll_in_seconds"]

    async with clean_database() as session:
        event_types = list(
            await session.scalars(
                select(TimelineEvent.event_type)
                .where(TimelineEvent.aggregate_id == account_id)
                .order_by(TimelineEvent.occurred_at, TimelineEvent.created_at)
            )
        )
    assert event_types == [
        "creator.poll.started",
        "creator.poll.failed",
        "creator.poll.started",
        "creator.poll.failed",
    ]


async def test_rate_limit_delays_same_account_without_polling(
    clean_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _creator_id, account_id, _external = await _seed_creator(clean_database)
    redis = FakeRedis()
    redis.hashes[f"poll_token_bucket:{Platform.MOCK.value}"] = {
        "tokens": 0.0,
        "updated_at": time.time(),
    }

    async def unexpected_poll(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("quota exhaustion must not call the adapter")

    monkeypatch.setattr(
        "app.workers.monitor_actors.poll_creator_platform_account", unexpected_poll
    )
    result = await run_creator_platform_account_poll(
        str(account_id), Platform.MOCK.value, redis=redis
    )
    schedule = RedisPollingSchedule(redis, Platform.MOCK.value)
    assert result["skipped"] == "PLATFORM_RATE_LIMITED"
    assert set(redis.sorted_sets[schedule.schedule_key]) == {str(account_id)}


async def test_worker_lock_acks_duplicate_without_second_platform_request(
    clean_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _creator_id, account_id, _external = await _seed_creator(clean_database)
    redis = FakeRedis()
    entered = asyncio.Event()
    resume = asyncio.Event()
    calls = 0

    async def blocking_poll(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        entered.set()
        await resume.wait()
        return {
            "creator_platform_account_id": str(account_id),
            "inserted": 0,
            "post_ids": [],
            "failures": [],
        }

    monkeypatch.setattr(
        "app.workers.monitor_actors.poll_creator_platform_account", blocking_poll
    )
    first_task = asyncio.create_task(
        run_creator_platform_account_poll(str(account_id), Platform.MOCK.value, redis=redis)
    )
    await entered.wait()
    duplicate = await run_creator_platform_account_poll(
        str(account_id), Platform.MOCK.value, redis=redis
    )
    resume.set()
    first = await first_task

    assert calls == 1
    assert duplicate["skipped"] == "POLL_LOCKED"
    assert first["failure_count"] == 0


async def test_scheduler_heartbeat_is_visible() -> None:
    redis = FakeRedis()
    await write_heartbeat(redis, "scheduler", ttl_seconds=30)
    assert await heartbeat_status(redis, ["scheduler", "worker-normal"]) == {
        "scheduler": True,
        "worker-normal": False,
    }
