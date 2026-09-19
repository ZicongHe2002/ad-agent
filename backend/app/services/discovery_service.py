from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.domain.enums import AuthStatus, MonitorState
from app.models import Creator, CreatorPlatformAccount, PlatformAuthorization, Post, PostContent
from app.platforms.errors import AuthorizationExpiredError, PlatformError, map_platform_exception
from app.platforms.runtime import runtime_registry
from app.repositories.outbox import OutboxRepository
from app.services.capability_service import capture_capability_snapshot
from app.services.content_service import normalize_content
from app.services.orchestration import write_timeline


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _validated_source_url(*candidates: object) -> str | None:
    """Return a platform-supplied HTTP(S) URL, without synthesizing one."""

    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        value = candidate.strip()
        if not value or len(value) > 2048 or any(char.isspace() for char in value):
            continue
        parsed = urlparse(value)
        if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
            return value
    return None


async def _poll_account(
    session: AsyncSession,
    creator: Creator,
    account: CreatorPlatformAccount,
) -> dict[str, Any]:
    started_at = utc_now()
    await write_timeline(
        session,
        job=None,
        event_type="creator.poll.started",
        aggregate_id=account.id,
        aggregate_type="CreatorPlatformAccount",
        payload={
            "creator_id": str(creator.id),
            "creator_platform_account_id": str(account.id),
            "platform": account.platform.value,
        },
    )

    try:
        adapter = runtime_registry.get(account.platform)
        page = await adapter.get_latest_posts(account)
    except PlatformError as exc:
        finished_at = utc_now()
        creator.last_checked_at = finished_at
        error = map_platform_exception(exc)
        failure: dict[str, Any] = {
            "platform": account.platform.value,
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        }
        retry_after = error.details.get("retry_after")
        if isinstance(retry_after, (int, float)):
            failure["retry_after_seconds"] = max(0.0, float(retry_after))
        if isinstance(exc, AuthorizationExpiredError):
            creator.monitor_state = MonitorState.ERROR
            if account.authorization_id is not None:
                authorization = await session.get(
                    PlatformAuthorization, account.authorization_id
                )
                if authorization is not None:
                    authorization.status = AuthStatus.EXPIRED
                    authorization.last_verified_at = finished_at
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
                "retry_after_seconds": failure.get("retry_after_seconds"),
                "monitor_paused": isinstance(exc, AuthorizationExpiredError),
                "duration_ms": max(
                    0, int((finished_at - started_at).total_seconds() * 1000)
                ),
            },
        )
        return {
            "creator_id": str(creator.id),
            "creator_platform_account_id": str(account.id),
            "inserted": 0,
            "post_ids": [],
            "failures": [failure],
        }

    snapshot = await capture_capability_snapshot(
        session, account.platform, tenant_id=creator.tenant_id
    )
    inserted: list[Post] = []
    outbox = OutboxRepository(session)
    for external in page.items:
        existing = await session.scalar(
            select(Post).where(
                Post.platform == account.platform,
                Post.external_post_id == external.external_post_id,
            )
        )
        if existing:
            if existing.source_url is None:
                existing.source_url = _validated_source_url(
                    external.source_url,
                    external.raw_payload.get("source_url"),
                    external.raw_payload.get("url"),
                )
            continue
        payload = external.model_dump(mode="json")
        raw_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        post = Post(
            platform=account.platform,
            external_post_id=external.external_post_id,
            source_url=_validated_source_url(
                external.source_url,
                external.raw_payload.get("source_url"),
                external.raw_payload.get("url"),
            ),
            creator_id=creator.id,
            published_at=external.published_at,
            detected_at=utc_now(),
            raw_payload_hash=raw_hash,
            source_capability_snapshot_id=snapshot.id,
        )
        session.add(post)
        await session.flush()
        normalized = normalize_content(payload)
        session.add(PostContent(post_id=post.id, **normalized.model_dump()))
        await outbox.append(
            aggregate_type="Post",
            aggregate_id=post.id,
            event_type="post.detected",
            payload={"post_id": str(post.id)},
            trace_id=post.id,
            idempotency_key=f"post-detected:{account.platform.value}:{external.external_post_id}",
        )
        await write_timeline(
            session,
            job=None,
            event_type="post.detected",
            aggregate_id=post.id,
            payload={
                "platform": account.platform.value,
                "external_post_id": external.external_post_id,
                "detection_latency_ms": max(
                    0,
                    int(
                        (_aware(post.detected_at) - _aware(post.published_at)).total_seconds()
                        * 1000
                    ),
                ),
            },
        )
        inserted.append(post)

    account.last_external_post_id = (
        page.items[0].external_post_id if page.items else account.last_external_post_id
    )
    finished_at = utc_now()
    creator.last_checked_at = finished_at
    if inserted:
        creator.last_post_at = max(item.published_at for item in inserted)
    await write_timeline(
        session,
        job=None,
        event_type="creator.poll.completed",
        aggregate_id=account.id,
        aggregate_type="CreatorPlatformAccount",
        payload={
            "creator_id": str(creator.id),
            "creator_platform_account_id": str(account.id),
            "platform": account.platform.value,
            "inserted": len(inserted),
            "duration_ms": max(0, int((finished_at - started_at).total_seconds() * 1000)),
        },
    )
    return {
        "creator_id": str(creator.id),
        "creator_platform_account_id": str(account.id),
        "inserted": len(inserted),
        "post_ids": [str(item.id) for item in inserted],
        "failures": [],
    }


async def poll_creator_platform_account(
    session: AsyncSession,
    creator_platform_account_id: UUID,
) -> dict[str, Any]:
    """Poll exactly one external identity, which is the scheduler's unit of work."""

    account = await session.get(CreatorPlatformAccount, creator_platform_account_id)
    if account is None:
        raise LookupError(
            f"CreatorPlatformAccount {creator_platform_account_id} was not found"
        )
    creator = await session.get(Creator, account.creator_id)
    if creator is None:
        raise LookupError(f"Creator {account.creator_id} was not found")
    if getattr(creator.monitor_state, "value", creator.monitor_state) != "ACTIVE":
        return {
            "creator_id": str(creator.id),
            "creator_platform_account_id": str(account.id),
            "inserted": 0,
            "post_ids": [],
            "failures": [],
            "skipped": "MONITOR_PAUSED",
        }
    return await _poll_account(session, creator, account)


async def poll_creator_accounts(session: AsyncSession, creator_id: UUID) -> dict[str, Any]:
    """Backward-compatible creator-wide poll used by the existing poll-now API."""

    creator = await session.get(Creator, creator_id)
    if creator is None:
        raise LookupError(f"Creator {creator_id} was not found")
    if getattr(creator.monitor_state, "value", creator.monitor_state) != "ACTIVE":
        return {"creator_id": str(creator_id), "inserted": 0, "skipped": "MONITOR_PAUSED"}
    accounts = (
        await session.scalars(
            select(CreatorPlatformAccount).where(CreatorPlatformAccount.creator_id == creator.id)
        )
    ).all()
    results = [await _poll_account(session, creator, account) for account in accounts]
    if not accounts:
        creator.last_checked_at = utc_now()
    return {
        "creator_id": str(creator.id),
        "inserted": sum(int(result["inserted"]) for result in results),
        "post_ids": [post_id for result in results for post_id in result["post_ids"]],
        "failures": [failure for result in results for failure in result["failures"]],
    }
