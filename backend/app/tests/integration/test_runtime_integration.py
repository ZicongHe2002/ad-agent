from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.api.v1.events import _database_events
from app.core.encryption import CredentialCipher
from app.core.security import hash_password
from app.domain.enums import UserRole, UserStatus
from app.main import app
from app.models import Tenant, TimelineEvent, User
from app.platforms.mock.persistent_service import PersistentMockPlatformService
from app.workers.broker import broker


async def test_persistent_mock_is_shared_across_service_instances(clean_database) -> None:
    first = PersistentMockPlatformService(clean_database)
    second = PersistentMockPlatformService(clean_database)
    await first.create_creator("shared", external_creator_id="shared-creator")
    await first.create_post("shared-creator", external_post_id="shared-post", title="shared title")
    loaded = await second.get_post("shared-post", inject_failure=False)
    assert loaded.title == "shared title"


def test_aes_gcm_round_trip_and_unique_nonce() -> None:
    cipher = CredentialCipher(b"x" * 32, key_version=7)
    first = cipher.encrypt("secret-token", associated_data=b"account")
    second = cipher.encrypt("secret-token", associated_data=b"account")
    assert first.nonce != second.nonce
    assert cipher.decrypt_text(first, associated_data=b"account") == "secret-token"
    assert first.key_version == 7


def test_dramatiq_asyncio_middleware_is_installed() -> None:
    assert "AsyncIO" in {type(item).__name__ for item in broker.middleware}


async def test_auth_and_error_envelope(clean_database) -> None:
    async with clean_database() as session, session.begin():
        tenant = Tenant(name="API", slug="api")
        session.add(tenant)
        await session.flush()
        session.add(
            User(
                tenant_id=tenant.id,
                email="api@example.com",
                display_name="API User",
                password_hash=hash_password("correct-password"),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        failed = await client.post(
            "/api/v1/auth/login",
            json={"email": "api@example.com", "password": "wrong"},
        )
        assert failed.status_code == 401
        assert failed.json()["error"]["code"] == "UNAUTHORIZED"
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "api@example.com", "password": "correct-password"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["display_name"] == "API User"
        metrics = await client.get(
            "/api/v1/metrics/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert metrics.status_code == 200


async def test_database_timeline_serializes_to_frontend_contract(clean_database) -> None:
    event_id = uuid4()
    trace_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    async with clean_database() as session, session.begin():
        session.add(
            TimelineEvent(
                id=event_id,
                event_type="test.event",
                aggregate_type="System",
                aggregate_id=uuid4(),
                trace_id=trace_id,
                payload={"value": 1},
                occurred_at=occurred_at,
            )
        )
    batch = await _database_events(
        None,
        replay_if_missing=True,
        since=occurred_at,
        creator_id=None,
        post_id=None,
        campaign_id=None,
        event_type="test.event",
        tenant_id=None,
        is_admin=True,
    )
    assert batch.cursor == str(event_id)
    assert batch.events == [
        {
            "event_id": str(event_id),
            "event_type": "test.event",
            "occurred_at": batch.events[0]["occurred_at"],
            "trace_id": str(trace_id),
            "creator_id": None,
            "post_id": None,
            "campaign_id": None,
            "payload": {"value": 1},
        }
    ]
