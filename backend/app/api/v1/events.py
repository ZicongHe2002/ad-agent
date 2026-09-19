from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.domain.enums import UserRole
from app.models import CommentJob, Creator, Post, TimelineEvent, User

router = APIRouter(prefix="/events", tags=["events"])


@dataclass
class EventHub:
    """Small in-process bridge for API-originated development events.

    Durable worker events are read from ``timeline_events`` below. This bridge is
    retained for Mock API events that happen before the monitor persists a Post.
    """

    history_size: int = 1000
    _history: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=1000))
    _subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "creator_id": payload.get("creator_id"),
            "post_id": payload.get("post_id"),
            "campaign_id": payload.get("campaign_id"),
            "payload": payload,
        }
        self._history.append(event)
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._subscribers.discard(queue)
        return event

    async def subscribe(self, last_event_id: str | None = None) -> AsyncGenerator[dict[str, Any], None]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        replay = last_event_id is None
        try:
            for event in tuple(self._history):
                if replay:
                    yield event
                elif event["event_id"] == last_event_id:
                    replay = True
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


event_hub = EventHub()


@dataclass(frozen=True)
class DatabaseEventBatch:
    events: list[dict[str, Any]]
    cursor: str | None


async def _database_events(
    last_event_id: str | None,
    *,
    replay_if_missing: bool,
    since: datetime,
    creator_id: UUID | None,
    post_id: UUID | None,
    campaign_id: UUID | None,
    event_type: str | None,
    tenant_id: UUID | None,
    is_admin: bool,
) -> DatabaseEventBatch:
    """Read committed timeline events so independent workers feed this stream."""

    async with AsyncSessionFactory() as session:
        marker: TimelineEvent | None = None
        if last_event_id:
            try:
                marker = await session.get(TimelineEvent, UUID(last_event_id))
            except ValueError:
                marker = None

        if marker is not None:
            statement = (
                select(TimelineEvent)
                .where(
                    or_(
                        TimelineEvent.occurred_at > marker.occurred_at,
                        and_(
                            TimelineEvent.occurred_at == marker.occurred_at,
                            TimelineEvent.id > marker.id,
                        ),
                    )
                )
                .order_by(TimelineEvent.occurred_at, TimelineEvent.id)
                .limit(100)
            )
            events = list((await session.scalars(statement)).all())
        elif replay_if_missing:
            newest = (
                await session.scalars(
                    select(TimelineEvent)
                    .order_by(TimelineEvent.occurred_at.desc(), TimelineEvent.id.desc())
                    .limit(100)
                )
            ).all()
            events = list(reversed(newest))
        else:
            events = list(
                (
                    await session.scalars(
                        select(TimelineEvent)
                        .where(TimelineEvent.occurred_at > since)
                        .order_by(TimelineEvent.occurred_at, TimelineEvent.id)
                        .limit(100)
                    )
                ).all()
            )

        # Advance past every scanned row, including rows filtered out below.
        # Otherwise a selective stream can repeatedly scan the same first 100
        # rows and never reach later matching events.
        cursor = str(events[-1].id) if events else last_event_id
        output: list[dict[str, Any]] = []
        for item in events:
            if event_type and item.event_type != event_type:
                continue
            job = (
                await session.get(CommentJob, item.comment_job_id) if item.comment_job_id else None
            )
            item_post_id = (
                job.post_id
                if job
                else (item.aggregate_id if item.aggregate_type == "Post" else None)
            )
            post = await session.get(Post, item_post_id) if item_post_id else None
            creator = await session.get(Creator, post.creator_id) if post else None
            item_campaign_id = job.campaign_id if job else None
            if not is_admin:
                item_tenant_id = job.tenant_id if job else (creator.tenant_id if creator else None)
                if tenant_id is None or item_tenant_id != tenant_id:
                    continue
            if creator_id and (creator is None or creator.id != creator_id):
                continue
            if post_id and item_post_id != post_id:
                continue
            if campaign_id and item_campaign_id != campaign_id:
                continue
            output.append(
                {
                    "event_id": str(item.id),
                    "event_type": item.event_type,
                    "occurred_at": item.occurred_at.isoformat(),
                    "trace_id": str(item.trace_id),
                    "creator_id": str(creator.id) if creator else None,
                    "post_id": str(item_post_id) if item_post_id else None,
                    "campaign_id": str(item_campaign_id) if item_campaign_id else None,
                    "payload": item.payload,
                }
            )
        return DatabaseEventBatch(events=output, cursor=cursor)


@router.get("/stream")
async def stream_events(
    request: Request,
    creator_id: UUID | None = Query(default=None),
    post_id: UUID | None = Query(default=None),
    campaign_id: UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    settings = get_settings()
    last_event_id = request.headers.get("last-event-id")
    is_admin = user.role == UserRole.ADMIN and user.tenant_id is None

    def matches(event: dict[str, Any]) -> bool:
        if not is_admin:
            if user.tenant_id is None or str(event.get("tenant_id")) != str(user.tenant_id):
                return False
        return all(
            expected is None or str(event.get(key)) == str(expected)
            for key, expected in (
                ("creator_id", creator_id),
                ("post_id", post_id),
                ("campaign_id", campaign_id),
                ("event_type", event_type),
            )
        )

    async def body() -> AsyncIterator[str]:
        iterator = event_hub.subscribe(last_event_id)
        pending_event = asyncio.create_task(iterator.__anext__())
        heartbeat = float(settings.sse_heartbeat_seconds)
        heartbeat_at = asyncio.get_running_loop().time() + heartbeat
        connected_at = datetime.now(timezone.utc)
        database_cursor = last_event_id
        first_database_read = True
        try:
            while not await request.is_disconnected():
                persisted = await _database_events(
                    database_cursor,
                    replay_if_missing=first_database_read,
                    since=connected_at,
                    creator_id=creator_id,
                    post_id=post_id,
                    campaign_id=campaign_id,
                    event_type=event_type,
                    tenant_id=user.tenant_id,
                    is_admin=is_admin,
                )
                first_database_read = False
                database_cursor = persisted.cursor
                for event in persisted.events:
                    yield (
                        f"id: {event['event_id']}\n"
                        f"event: {event['event_type']}\n"
                        f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    )
                    heartbeat_at = asyncio.get_running_loop().time() + heartbeat
                # A polling timeout must not cancel __anext__: cancellation closes
                # the async subscription generator and breaks the next read.
                done, _ = await asyncio.wait({pending_event}, timeout=0.5)
                if not done:
                    if asyncio.get_running_loop().time() >= heartbeat_at:
                        yield ": heartbeat\n\n"
                        heartbeat_at = asyncio.get_running_loop().time() + heartbeat
                    continue
                event = pending_event.result()
                pending_event = asyncio.create_task(iterator.__anext__())
                if matches(event):
                    yield (
                        f"id: {event['event_id']}\n"
                        f"event: {event['event_type']}\n"
                        f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    )
        finally:
            pending_event.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending_event
            await iterator.aclose()

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
