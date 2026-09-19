from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.domain.enums import MonitorState, Platform
from app.models import Creator, CreatorPlatformAccount
from app.services.maintenance_service import MaintenanceResult, run_maintenance_once

from .health import write_heartbeat

CLAIM_DUE_SCRIPT = """
local schedule = KEYS[1]
local leases = KEYS[2]
local now = tonumber(ARGV[1])
local lease_until = tonumber(ARGV[2])
local count = tonumber(ARGV[3])
local due = redis.call('ZRANGEBYSCORE', schedule, '-inf', now, 'LIMIT', 0, count)
for _, member in ipairs(due) do
  redis.call('ZREM', schedule, member)
  redis.call('ZADD', leases, lease_until, member)
end
return due
"""


REQUEUE_EXPIRED_SCRIPT = """
local leases = KEYS[1]
local schedule = KEYS[2]
local now = tonumber(ARGV[1])
local count = tonumber(ARGV[2])
local expired = redis.call('ZRANGEBYSCORE', leases, '-inf', now, 'LIMIT', 0, count)
for _, member in ipairs(expired) do
  redis.call('ZREM', leases, member)
  redis.call('ZADD', schedule, now, member)
end
return expired
"""


class RedisPollingSchedule:
    """A leased schedule that cannot permanently lose jobs between pop and enqueue."""

    def __init__(self, redis: Any, platform: str, lease_seconds: int = 60) -> None:
        self.redis = redis
        self.schedule_key = f"poll_schedule:{platform}"
        self.lease_key = f"poll_schedule_leases:{platform}"
        self.lease_seconds = lease_seconds

    async def schedule(self, account_id: str, at_timestamp: float) -> None:
        await self.redis.zadd(self.schedule_key, {account_id: at_timestamp})

    async def claim_due(self, now: float | None = None, limit: int = 100) -> list[str]:
        timestamp = now if now is not None else time.time()
        values = await self.redis.eval(
            CLAIM_DUE_SCRIPT,
            2,
            self.schedule_key,
            self.lease_key,
            timestamp,
            timestamp + self.lease_seconds,
            limit,
        )
        return [item.decode() if isinstance(item, bytes) else str(item) for item in values]

    async def complete(self, account_id: str, next_at: float) -> None:
        pipe = self.redis.pipeline(transaction=True)
        pipe.zrem(self.lease_key, account_id)
        pipe.zadd(self.schedule_key, {account_id: next_at})
        await pipe.execute()

    async def abandon(self, account_id: str) -> None:
        """Remove a terminal/stale lease without creating another poll."""

        await self.redis.zrem(self.lease_key, account_id)

    async def requeue(self, account_id: str, at_timestamp: float) -> None:
        """Return a lease to the schedule when broker dispatch itself failed."""

        pipe = self.redis.pipeline(transaction=True)
        pipe.zrem(self.lease_key, account_id)
        pipe.zadd(self.schedule_key, {account_id: at_timestamp})
        await pipe.execute()

    async def requeue_expired(self, now: float | None = None, limit: int = 100) -> list[str]:
        timestamp = now if now is not None else time.time()
        values = await self.redis.eval(
            REQUEUE_EXPIRED_SCRIPT,
            2,
            self.lease_key,
            self.schedule_key,
            timestamp,
            limit,
        )
        return [item.decode() if isinstance(item, bytes) else str(item) for item in values]


logger = logging.getLogger(__name__)
MAINTENANCE_INTERVAL_SECONDS = 15.0


async def _seed_missing(redis: Any) -> None:
    now = time.time()
    async with AsyncSessionFactory() as session:
        rows = (
            await session.execute(
                select(CreatorPlatformAccount, Creator)
                .join(Creator, Creator.id == CreatorPlatformAccount.creator_id)
                .where(Creator.monitor_state == MonitorState.ACTIVE)
            )
        ).all()
        for account, _creator in rows:
            try:
                schedule = RedisPollingSchedule(redis, account.platform.value)
                scheduled = await redis.zscore(schedule.schedule_key, str(account.id))
                leased = await redis.zscore(schedule.lease_key, str(account.id))
                if scheduled is None and leased is None:
                    await schedule.schedule(str(account.id), now)
            except Exception:
                logger.exception(
                    "poll schedule seed failed creator_platform_account_id=%s",
                    account.id,
                )


async def _dispatch_platform(redis: Any, platform: Platform) -> int:
    schedule = RedisPollingSchedule(redis, platform.value)
    await schedule.requeue_expired(limit=100)
    due = await schedule.claim_due(limit=100)
    if not due:
        return 0
    from app.workers.monitor_actors import (
        poll_creator_account,
        poll_creator_account_high_priority,
    )

    dispatched = 0
    for account_id in due:
        try:
            parsed_account_id = UUID(account_id)
        except ValueError:
            logger.error(
                "invalid account id in polling schedule platform=%s account_id=%r",
                platform.value,
                account_id,
            )
            await schedule.abandon(account_id)
            continue
        try:
            async with AsyncSessionFactory() as session:
                account = await session.get(CreatorPlatformAccount, parsed_account_id)
                if account is None:
                    await schedule.abandon(account_id)
                    continue
                creator = await session.get(Creator, account.creator_id)
                if creator is None or creator.monitor_state != MonitorState.ACTIVE:
                    await schedule.abandon(account_id)
                    continue
                actor = (
                    poll_creator_account_high_priority
                    if creator.priority >= 90
                    else poll_creator_account
                )
                actor.send(str(account.id), platform.value)
        except Exception:
            logger.exception(
                "poll dispatch failed",
                extra={
                    "creator_platform_account_id": account_id,
                    "platform": platform.value,
                },
            )
            try:
                await schedule.requeue(account_id, time.time() + 1)
            except Exception:
                logger.exception(
                    "poll lease requeue failed creator_platform_account_id=%s platform=%s",
                    account_id,
                    platform.value,
                )
            continue
        dispatched += 1
    return dispatched


async def _run_maintenance_cycle() -> MaintenanceResult:
    """Commit recovery state and outbox records atomically before relay delivery."""

    async with AsyncSessionFactory() as session:
        result = await run_maintenance_once(session)
        await session.commit()
        return result


async def _dispatch_all_platforms(redis: Any) -> int:
    processed = 0
    for platform in Platform:
        try:
            processed += await _dispatch_platform(redis, platform)
        except Exception:
            # One corrupt schedule or unavailable platform must not stop the
            # remaining platform schedules or periodic maintenance.
            logger.exception("platform polling dispatch failed platform=%s", platform.value)
    return processed


async def run() -> None:
    from redis.asyncio import Redis

    redis = Redis.from_url(get_settings().redis_url)
    last_seed = 0.0
    last_heartbeat = 0.0
    last_maintenance = 0.0
    try:
        while True:
            now = time.time()
            if now - last_heartbeat >= 10:
                try:
                    await write_heartbeat(redis, "scheduler")
                    last_heartbeat = now
                except Exception:
                    logger.exception("scheduler heartbeat failed")
            if now - last_seed >= 30:
                try:
                    await _seed_missing(redis)
                    last_seed = now
                except Exception:
                    logger.exception("poll schedule seed failed")
            if now - last_maintenance >= MAINTENANCE_INTERVAL_SECONDS:
                try:
                    maintenance = await _run_maintenance_cycle()
                    last_maintenance = now
                    if maintenance.errors:
                        logger.warning(
                            "maintenance cycle completed with isolated failures operations=%s",
                            maintenance.errors,
                        )
                except Exception:
                    logger.exception("maintenance cycle failed")
            processed = await _dispatch_all_platforms(redis)
            await asyncio.sleep(0 if processed else 0.5)
    finally:
        await redis.close()


if __name__ == "__main__":
    asyncio.run(run())
