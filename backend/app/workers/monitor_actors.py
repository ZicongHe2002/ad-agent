from __future__ import annotations

import math
import time
from datetime import timezone
from typing import Any, cast
from uuid import UUID

import dramatiq
from sqlalchemy import select

from app.core.clock import utc_now
from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.domain.enums import AuthStatus, CapabilityStatus, MonitorState, Platform
from app.models import Creator, CreatorPlatformAccount, PlatformAuthorization, Post
from app.platforms.errors import map_platform_exception
from app.services.capability_service import effective_capabilities
from app.services.circuit_breaker_service import RedisCircuitBreaker
from app.services.discovery_service import poll_creator_platform_account
from app.services.monitor_service import (
    SCHEDULABLE_CAPABILITIES,
    PollingContext,
    RedisPlatformRatePressure,
    RedisPlatformTokenBucket,
    RedisPollFailureTracker,
    RedisPollLock,
    next_poll_interval,
    polling_window_flags,
    recent_activity_score,
)
from app.services.orchestration import write_timeline

from .broker import PERSISTENT_DLQ_ACTOR, QUEUE_HIGH, QUEUE_NORMAL
from .scheduler import RedisPollingSchedule


async def _polling_context(
    session: Any,
    account: CreatorPlatformAccount,
    creator: Creator,
    *,
    failure_count: int,
    rate_limit_pressure: float = 0.0,
) -> PollingContext:
    capabilities, _records = await effective_capabilities(session, account.platform)
    capability_status = capabilities.latest_posts.value
    authorization = (
        await session.get(PlatformAuthorization, account.authorization_id)
        if account.authorization_id is not None
        else None
    )
    auth_invalid = False
    if capability_status == CapabilityStatus.AUTH_REQUIRED.value:
        auth_invalid = authorization is None or authorization.status != AuthStatus.VALID
    if authorization is not None:
        expires_at = authorization.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            auth_invalid = auth_invalid or expires_at <= utc_now()
        auth_invalid = auth_invalid or authorization.status in {
            AuthStatus.EXPIRED,
            AuthStatus.REVOKED,
            AuthStatus.ERROR,
        }
    recent_posts = list(
        await session.scalars(
            select(Post.published_at)
            .where(Post.creator_id == creator.id)
            .order_by(Post.published_at.desc())
            .limit(5)
        )
    )
    in_expected_window, in_high_probability_window = polling_window_flags(
        creator.expected_publish_windows,
        now=utc_now(),
    )
    return PollingContext(
        creator_platform_account_id=str(account.id),
        normal_interval_sec=creator.normal_poll_interval_sec,
        warm_interval_sec=creator.warm_poll_interval_sec,
        hot_interval_sec=creator.hot_poll_interval_sec,
        priority=creator.priority,
        in_expected_publish_window=in_expected_window,
        in_high_probability_window=in_high_probability_window,
        recent_activity_score=recent_activity_score(recent_posts, now=utc_now()),
        failure_count=failure_count,
        platform_rate_limit_pressure=rate_limit_pressure,
        capability_status=capability_status,
        auth_invalid=auth_invalid,
        monitor_paused=creator.monitor_state != MonitorState.ACTIVE,
    )


async def _record_unexpected_failure(
    account_id: UUID,
    exc: BaseException,
    *,
    duration_ms: int,
) -> None:
    error = map_platform_exception(exc)
    async with AsyncSessionFactory() as session:
        account = await session.get(CreatorPlatformAccount, account_id)
        if account is None:
            return
        creator = await session.get(Creator, account.creator_id)
        if creator is None:
            return
        creator.last_checked_at = utc_now()
        await write_timeline(
            session,
            job=None,
            event_type="creator.poll.failed",
            aggregate_id=account.id,
            aggregate_type="CreatorPlatformAccount",
            payload={
                "creator_id": str(creator.id),
                "creator_platform_account_id": str(account.id),
                "platform": account.platform.value,
                "code": error.code,
                "retryable": error.retryable,
                "duration_ms": max(0, duration_ms),
            },
        )
        await session.commit()


async def _schedule_after_poll(
    redis: Any,
    account_id: UUID,
    *,
    failure_count: int,
    minimum_delay_seconds: int = 0,
) -> int | None:
    async with AsyncSessionFactory() as session:
        account = await session.get(CreatorPlatformAccount, account_id)
        if account is None:
            return None
        creator = await session.get(Creator, account.creator_id)
        if creator is None:
            return None
        pressure_tracker = RedisPlatformRatePressure(redis, account.platform.value)
        pressure = await pressure_tracker.current()
        context = await _polling_context(
            session,
            account,
            creator,
            failure_count=failure_count,
            rate_limit_pressure=pressure,
        )
        interval = max(minimum_delay_seconds, next_poll_interval(context))
        await RedisPollingSchedule(redis, account.platform.value).complete(
            str(account.id), time.time() + interval
        )
        return interval


async def run_creator_platform_account_poll(
    creator_platform_account_id: str,
    platform_hint: str | None = None,
    *,
    redis: Any | None = None,
) -> dict[str, Any]:
    """Execute one scheduled account poll and acknowledge its Redis lease.

    ``redis`` is injectable for deterministic integration tests.  Production
    actors create a connection from the configured URL.
    """

    from redis.asyncio import Redis

    account_id = UUID(creator_platform_account_id)
    owns_redis = redis is None
    redis_client: Any = redis or Redis.from_url(get_settings().redis_url)
    platform: Platform | None = None
    creator: Creator | None = None
    account: CreatorPlatformAccount | None = None
    async with AsyncSessionFactory() as session:
        account = await session.get(CreatorPlatformAccount, account_id)
        if account is not None:
            platform = account.platform
            creator = await session.get(Creator, account.creator_id)

    hinted_platform = Platform(platform_hint) if platform_hint is not None else None
    schedule_platform = platform or hinted_platform
    if account is None or creator is None:
        if schedule_platform is not None:
            await RedisPollingSchedule(redis_client, schedule_platform.value).abandon(
                creator_platform_account_id
            )
        if owns_redis:
            await redis_client.close()
        return {
            "creator_platform_account_id": creator_platform_account_id,
            "inserted": 0,
            "skipped": "ACCOUNT_NOT_FOUND",
        }
    platform = account.platform
    if creator.monitor_state != MonitorState.ACTIVE:
        await RedisPollingSchedule(redis_client, platform.value).abandon(
            creator_platform_account_id
        )
        if owns_redis:
            await redis_client.close()
        return {
            "creator_id": str(creator.id),
            "creator_platform_account_id": creator_platform_account_id,
            "inserted": 0,
            "skipped": "MONITOR_PAUSED",
        }

    lock = RedisPollLock(redis_client, creator_platform_account_id)
    if not await lock.acquire():
        if owns_redis:
            await redis_client.close()
        return {
            "creator_id": str(creator.id),
            "creator_platform_account_id": creator_platform_account_id,
            "inserted": 0,
            "skipped": "POLL_LOCKED",
        }

    failure_tracker = RedisPollFailureTracker(redis_client, creator_platform_account_id)
    pressure_tracker = RedisPlatformRatePressure(redis_client, platform.value)
    circuit = RedisCircuitBreaker(redis_client, platform.value, "get_latest_posts")
    started = time.monotonic()
    try:
        existing_failures = await failure_tracker.current()
        rate_pressure = await pressure_tracker.current()
        async with AsyncSessionFactory() as session:
            current_account = await session.get(CreatorPlatformAccount, account_id)
            current_creator = (
                await session.get(Creator, current_account.creator_id)
                if current_account is not None
                else None
            )
            if current_account is None or current_creator is None:
                await RedisPollingSchedule(redis_client, platform.value).abandon(
                    creator_platform_account_id
                )
                return {
                    "creator_platform_account_id": creator_platform_account_id,
                    "inserted": 0,
                    "skipped": "ACCOUNT_NOT_FOUND",
                }
            policy = await _polling_context(
                session,
                current_account,
                current_creator,
                failure_count=existing_failures,
                rate_limit_pressure=rate_pressure,
            )
            if policy.auth_invalid:
                current_creator.monitor_state = MonitorState.ERROR
                authorization = (
                    await session.get(
                        PlatformAuthorization,
                        current_account.authorization_id,
                    )
                    if current_account.authorization_id is not None
                    else None
                )
                if authorization is not None:
                    expires_at = authorization.expires_at
                    if expires_at is not None:
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                        if expires_at <= utc_now():
                            authorization.status = AuthStatus.EXPIRED
                    authorization.last_verified_at = utc_now()
                await write_timeline(
                    session,
                    job=None,
                    event_type="creator.poll.failed",
                    aggregate_id=current_account.id,
                    aggregate_type="CreatorPlatformAccount",
                    payload={
                        "creator_id": str(current_creator.id),
                        "creator_platform_account_id": str(current_account.id),
                        "platform": current_account.platform.value,
                        "code": "authorization_invalid",
                        "retryable": False,
                        "monitor_paused": True,
                        "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                    },
                )
                await session.commit()
        if policy.capability_status not in SCHEDULABLE_CAPABILITIES or policy.auth_invalid:
            if policy.auth_invalid:
                await RedisPollingSchedule(redis_client, platform.value).abandon(
                    creator_platform_account_id
                )
                return {
                    "creator_id": str(creator.id),
                    "creator_platform_account_id": creator_platform_account_id,
                    "inserted": 0,
                    "skipped": "AUTH_INVALID",
                    "monitor_paused": True,
                }
            defer_interval = next_poll_interval(policy)
            await RedisPollingSchedule(redis_client, platform.value).complete(
                creator_platform_account_id,
                time.time() + defer_interval,
            )
            return {
                "creator_id": str(creator.id),
                "creator_platform_account_id": creator_platform_account_id,
                "inserted": 0,
                "skipped": f"CAPABILITY_{policy.capability_status}",
                "next_poll_in_seconds": defer_interval,
            }

        quota = await RedisPlatformTokenBucket(redis_client, platform.value).acquire()
        if not quota.allowed:
            await pressure_tracker.record_limited()
            interval = await _schedule_after_poll(
                redis_client,
                account_id,
                failure_count=existing_failures,
                minimum_delay_seconds=quota.retry_after_seconds,
            )
            return {
                "creator_id": str(creator.id),
                "creator_platform_account_id": creator_platform_account_id,
                "inserted": 0,
                "skipped": "PLATFORM_RATE_LIMITED",
                "retry_after_seconds": quota.retry_after_seconds,
                "next_poll_in_seconds": interval,
            }

        # Acquire the circuit probe only once quota is available. Otherwise a
        # HALF_OPEN probe could be stranded without making a platform request.
        circuit_decision = await circuit.acquire()
        if not circuit_decision.allowed:
            await RedisPollingSchedule(redis_client, platform.value).complete(
                creator_platform_account_id,
                time.time() + circuit_decision.retry_after_seconds,
            )
            return {
                "creator_id": str(creator.id),
                "creator_platform_account_id": creator_platform_account_id,
                "inserted": 0,
                "skipped": "PLATFORM_CIRCUIT_OPEN",
                "retry_after_seconds": circuit_decision.retry_after_seconds,
            }

        try:
            async with AsyncSessionFactory() as session:
                result = await poll_creator_platform_account(session, account_id)
                await session.commit()
        except Exception as exc:
            failure_count = await failure_tracker.record_failure()
            await circuit.record_failure()
            await _record_unexpected_failure(
                account_id,
                exc,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            interval = await _schedule_after_poll(
                redis_client,
                account_id,
                failure_count=failure_count,
            )
            return {
                "creator_id": str(creator.id),
                "creator_platform_account_id": creator_platform_account_id,
                "inserted": 0,
                "failures": [
                    {
                        "platform": platform.value,
                        "code": map_platform_exception(exc).code,
                    }
                ],
                "failure_count": failure_count,
                "next_poll_in_seconds": interval,
            }

        if result.get("failures"):
            failure_count = await failure_tracker.record_failure()
            rate_limited = any(
                item.get("code") == "rate_limited" for item in result["failures"]
            )
            if rate_limited:
                await pressure_tracker.record_limited()
            availability_failure = any(
                bool(item.get("retryable")) and item.get("code") != "rate_limited"
                for item in result["failures"]
            )
            if availability_failure:
                await circuit.record_failure()
            else:
                # 429/auth/policy responses prove the endpoint is reachable and
                # must release a HALF_OPEN probe rather than opening the circuit.
                await circuit.record_success()
            retry_after_seconds = max(
                (
                    math.ceil(float(item.get("retry_after_seconds", 0)))
                    for item in result["failures"]
                    if isinstance(item.get("retry_after_seconds"), (int, float))
                ),
                default=0,
            )
        else:
            await failure_tracker.reset()
            await pressure_tracker.reset()
            await circuit.record_success()
            failure_count = 0
            retry_after_seconds = 0
        interval = await _schedule_after_poll(
            redis_client,
            account_id,
            failure_count=failure_count,
            minimum_delay_seconds=retry_after_seconds,
        )
        result["failure_count"] = failure_count
        result["next_poll_in_seconds"] = interval
        return result
    finally:
        await lock.release()
        if owns_redis:
            await redis_client.close()


@dramatiq.actor(
    queue_name=QUEUE_NORMAL,
    max_retries=5,
    min_backoff=1000,
    max_backoff=60_000,
    on_retry_exhausted=PERSISTENT_DLQ_ACTOR,
)
async def poll_creator(creator_id: str) -> dict[str, Any]:
    """Compatibility actor for ``POST /creators/{id}/poll-now``."""

    from redis.asyncio import Redis

    creator_uuid = UUID(creator_id)
    async with AsyncSessionFactory() as session:
        account_ids = list(
            await session.scalars(
                select(CreatorPlatformAccount.id).where(
                    CreatorPlatformAccount.creator_id == creator_uuid
                )
            )
        )
        creator = await session.get(Creator, creator_uuid)
        if creator is None:
            raise LookupError(f"Creator {creator_uuid} was not found")
    redis = Redis.from_url(get_settings().redis_url)
    try:
        results = [
            await run_creator_platform_account_poll(str(account_id), redis=redis)
            for account_id in account_ids
        ]
    finally:
        await redis.close()
    return {
        "creator_id": creator_id,
        "inserted": sum(int(result.get("inserted", 0)) for result in results),
        "post_ids": [post_id for result in results for post_id in result.get("post_ids", [])],
        "failures": [failure for result in results for failure in result.get("failures", [])],
        "account_results": results,
    }


@dramatiq.actor(
    queue_name=QUEUE_HIGH,
    max_retries=2,
    on_retry_exhausted=PERSISTENT_DLQ_ACTOR,
)
async def poll_creator_high_priority(creator_id: str) -> dict[str, Any]:
    return cast(dict[str, Any], await poll_creator.fn(creator_id))


@dramatiq.actor(
    queue_name=QUEUE_NORMAL,
    max_retries=2,
    on_retry_exhausted=PERSISTENT_DLQ_ACTOR,
)
async def poll_creator_account(
    creator_platform_account_id: str,
    platform_hint: str | None = None,
) -> dict[str, Any]:
    return await run_creator_platform_account_poll(
        creator_platform_account_id,
        platform_hint,
    )


@dramatiq.actor(
    queue_name=QUEUE_HIGH,
    max_retries=2,
    on_retry_exhausted=PERSISTENT_DLQ_ACTOR,
)
async def poll_creator_account_high_priority(
    creator_platform_account_id: str,
    platform_hint: str | None = None,
) -> dict[str, Any]:
    return await run_creator_platform_account_poll(
        creator_platform_account_id,
        platform_hint,
    )
