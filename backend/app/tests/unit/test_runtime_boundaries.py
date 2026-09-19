from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1 import events
from app.core.config import Settings
from app.domain.enums import UserRole
from app.models import User


@pytest.mark.parametrize("environment", ["production", "staging"])
@pytest.mark.parametrize("secret", ["local-development-only-change-me", "short", "a" * 64])
def test_deployment_rejects_unsafe_jwt_secret(environment, secret):
    with pytest.raises(ValidationError, match="APP_SECRET_KEY"):
        Settings(_env_file=None, app_env=environment, app_secret_key=secret)


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_deployment_accepts_generated_secret(environment):
    settings = Settings(
        _env_file=None,
        app_env=environment,
        app_secret_key="53a9da8af0704b9ca73265f9f9fa11f0b772cfe7b72648929c0c4d5910b04b30",
    )
    assert settings.app_env == environment


def test_development_keeps_local_default(monkeypatch):
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    assert Settings(_env_file=None, app_env="development").app_secret_key


class StreamRequest:
    def __init__(self):
        self.headers: dict[str, str] = {}
        self.disconnected = False

    async def is_disconnected(self):
        return self.disconnected


async def _stream(monkeypatch, *, heartbeat=0.01):
    hub = events.EventHub()

    async def empty_database(*_args, **_kwargs):
        return events.DatabaseEventBatch([], None)

    monkeypatch.setattr(events, "event_hub", hub)
    monkeypatch.setattr(events, "_database_events", empty_database)
    monkeypatch.setattr(events, "get_settings", lambda: SimpleNamespace(sse_heartbeat_seconds=heartbeat))
    request = StreamRequest()
    response = await events.stream_events(
        request, creator_id=None, post_id=None, campaign_id=None, event_type=None,
        user=User(id=uuid4(), role=UserRole.ADMIN, tenant_id=None),
    )
    return hub, request, response.body_iterator


async def test_idle_stream_keeps_subscription_and_receives_later_event(monkeypatch):
    hub, _request, body = await _stream(monkeypatch)
    assert await asyncio.wait_for(body.__anext__(), timeout=2) == ": heartbeat\n\n"
    assert len(hub._subscribers) == 1
    event = await hub.publish("post.detected", {"post_id": "later"})
    message = await asyncio.wait_for(body.__anext__(), timeout=2)
    assert event["event_id"] in message
    assert '"post_id": "later"' in message
    await body.aclose()
    assert not hub._subscribers


async def test_disconnected_stream_closes_subscription(monkeypatch):
    hub, request, body = await _stream(monkeypatch)
    await asyncio.wait_for(body.__anext__(), timeout=2)
    request.disconnected = True
    with pytest.raises(StopAsyncIteration):
        await body.__anext__()
    assert not hub._subscribers


async def test_cancelled_stream_cleans_up_pending_event_read(monkeypatch):
    hub, _request, body = await _stream(monkeypatch, heartbeat=15)
    task = asyncio.create_task(body.__anext__())
    await asyncio.sleep(0.01)
    assert hub._subscribers
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not hub._subscribers
