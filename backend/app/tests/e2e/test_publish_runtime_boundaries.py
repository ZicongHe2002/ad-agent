from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, text

from app.core.clock import utc_now
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.enums import BrandStatus, CommentJobState, TenantStatus
from app.main import app
from app.models import (
    Brand,
    BrandAccount,
    CommentCandidate,
    CommentJob,
    OutboxEvent,
    PublishingSettings,
    PublishJob,
    Tenant,
)
from app.platforms.base import ReconcileResult
from app.platforms.errors import PlatformTemporaryError
from app.platforms.runtime import mock_service, runtime_registry
from app.services import publisher_runtime
from app.services.maintenance_service import (
    enqueue_due_publish_retries,
    enqueue_due_reconciliations,
)
from app.services.pipeline_service import analyze_post
from app.services.publish_retry_policy import (
    MAX_PUBLISH_ATTEMPTS,
    MAX_RECONCILE_ATTEMPTS,
    PublishAttemptDeferred,
    reconciliation_attempts,
)
from app.services.publishing_policy_service import publishing_scope_key
from app.tests.e2e.test_publishing_modes import setup_case
from app.workers import publish_actors


async def _ready(factory):
    context = await setup_case(factory)
    async with factory() as session:
        await analyze_post(session, context["post_id"])
        publish = await session.scalar(select(PublishJob))
        context["publish_id"] = publish.id
        await session.commit()
    return context


@pytest.mark.parametrize("operation", ["publish", "reconcile"])
async def test_early_duplicate_delivery_never_calls_platform(clean_database, monkeypatch, operation):
    context = await _ready(clean_database)
    async with clean_database() as session:
        publish = await session.get(PublishJob, context["publish_id"])
        job = await session.get(CommentJob, publish.comment_job_id)
        state = CommentJobState.READY_FOR_RETRY if operation == "publish" else CommentJobState.PUBLISH_UNCERTAIN
        publish.state = job.state = state
        publish.attempt_count = 1
        publish.next_retry_at = utc_now() + timedelta(hours=1)
        await session.commit()
        adapter = runtime_registry.get(publish.platform)
        call = AsyncMock()
        monkeypatch.setattr(adapter, "publish_top_level_comment" if operation == "publish" else "reconcile_publish", call)
        if operation == "publish":
            with pytest.raises(PublishAttemptDeferred, match="RETRY_NOT_DUE"):
                await publisher_runtime.publish_comment_job(session, publish.id)
        else:
            await publisher_runtime.reconcile_publish_job(session, publish.id)
        call.assert_not_called()
        assert publish.attempt_count == 1


async def test_exhausted_publish_retry_finishes_instead_of_being_reenqueued(clean_database):
    context = await _ready(clean_database)
    async with clean_database() as session:
        publish = await session.get(PublishJob, context["publish_id"])
        job = await session.get(CommentJob, publish.comment_job_id)
        publish.state = job.state = CommentJobState.READY_FOR_RETRY
        publish.attempt_count = MAX_PUBLISH_ATTEMPTS
        await session.commit()
        now = utc_now() + timedelta(minutes=1)
        before = await session.scalar(select(func.count()).select_from(OutboxEvent))
        assert await enqueue_due_publish_retries(session, now=now) == []
        await session.commit()
        assert publish.state == job.state == CommentJobState.FAILED
        assert publish.next_retry_at is None
        assert publish.finished_at is not None
        assert await enqueue_due_publish_retries(session, now=now + timedelta(minutes=1)) == []
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == before


async def test_direct_publish_call_also_enforces_attempt_limit(clean_database, monkeypatch):
    context = await _ready(clean_database)
    async with clean_database() as session:
        publish = await session.get(PublishJob, context["publish_id"])
        job = await session.get(CommentJob, publish.comment_job_id)
        publish.state = job.state = CommentJobState.READY_FOR_RETRY
        publish.attempt_count = MAX_PUBLISH_ATTEMPTS
        adapter = runtime_registry.get(publish.platform)
        call = AsyncMock()
        monkeypatch.setattr(adapter, "publish_top_level_comment", call)
        with pytest.raises(PublishAttemptDeferred, match="PUBLISH_ATTEMPTS_EXHAUSTED"):
            await publisher_runtime.publish_comment_job(session, publish.id)
        await session.commit()
        assert publish.state == job.state == CommentJobState.FAILED
        call.assert_not_called()


async def test_last_publish_attempt_reconciles_before_final_failure(clean_database, monkeypatch):
    context = await _ready(clean_database)
    async with clean_database() as session:
        publish = await session.get(PublishJob, context["publish_id"])
        job = await session.get(CommentJob, publish.comment_job_id)
        publish.state = job.state = CommentJobState.PUBLISH_UNCERTAIN
        publish.attempt_count = MAX_PUBLISH_ATTEMPTS
        await session.commit()
        call = AsyncMock(return_value=ReconcileResult(found=False, status="NOT_FOUND"))
        monkeypatch.setattr(runtime_registry.get(publish.platform), "reconcile_publish", call)
        await publisher_runtime.reconcile_publish_job(session, publish.id)
        await session.commit()
        call.assert_awaited_once()
        assert publish.state == job.state == CommentJobState.FAILED
        assert publish.next_retry_at is None


async def test_reconciliation_failures_have_durable_bounded_attempts(clean_database, monkeypatch):
    context = await _ready(clean_database)
    async with clean_database() as session:
        publish = await session.get(PublishJob, context["publish_id"])
        job = await session.get(CommentJob, publish.comment_job_id)
        publish.state = job.state = CommentJobState.PUBLISH_UNCERTAIN
        publish.attempt_count = 1
        await session.commit()
        call = AsyncMock(side_effect=PlatformTemporaryError("temporary"))
        monkeypatch.setattr(runtime_registry.get(publish.platform), "reconcile_publish", call)
    for attempt in range(MAX_RECONCILE_ATTEMPTS):
        async with clean_database() as session:
            publish = await session.get(PublishJob, context["publish_id"])
            publish.next_retry_at = utc_now() - timedelta(seconds=1)
            await session.commit()
            with pytest.raises(PlatformTemporaryError):
                await publisher_runtime.reconcile_publish_job(session, publish.id)
            await session.rollback()
        async with clean_database() as session:
            publish = await session.get(PublishJob, context["publish_id"])
            assert reconciliation_attempts(publish) == attempt + 1
    async with clean_database() as session:
        assert await enqueue_due_reconciliations(session, now=utc_now() + timedelta(minutes=5)) == []
        await session.commit()
        publish = await session.get(PublishJob, context["publish_id"])
        assert publish.state == CommentJobState.FAILED
        assert publish.last_error_code == "reconciliation_attempts_exhausted"
    assert call.await_count == MAX_RECONCILE_ATTEMPTS


@pytest.mark.parametrize("disabled", ["brand", "tenant", "disclosure"])
async def test_queued_publish_rechecks_current_operating_policy(clean_database, disabled):
    context = await _ready(clean_database)
    async with clean_database() as session:
        if disabled == "brand":
            brand = await session.scalar(select(Brand))
            brand.status = BrandStatus.PAUSED
        elif disabled == "tenant":
            tenant = await session.get(Tenant, context["tenant_id"])
            tenant.status = TenantStatus.SUSPENDED
        else:
            policy = await session.get(PublishingSettings, publishing_scope_key(context["tenant_id"]))
            policy.auto_disclosure_enabled = False
        await session.commit()
    async with clean_database() as session:
        with pytest.raises(PermissionError):
            await publisher_runtime.publish_comment_job(session, context["publish_id"])
    assert (await mock_service.get_comments("auto-mode-post", inject_failure=False)).items == []


async def test_actor_persists_blocked_state_after_review_mode_is_reenabled(clean_database, monkeypatch):
    context = await _ready(clean_database)
    async with clean_database() as session:
        policy = await session.get(PublishingSettings, publishing_scope_key(context["tenant_id"]))
        policy.mode = "REVIEW"
        await session.commit()
    circuit = SimpleNamespace(
        acquire=AsyncMock(return_value=SimpleNamespace(allowed=True)),
        record_success=AsyncMock(),
    )
    monkeypatch.setattr(publish_actors, "RedisCircuitBreaker", lambda *_args: circuit)
    result = await publish_actors.publish_comment.fn.__wrapped__(str(context["publish_id"]))
    assert result["state"] == "BLOCKED"
    async with clean_database() as session:
        publish = await session.get(PublishJob, context["publish_id"])
        job = await session.get(CommentJob, publish.comment_job_id)
        assert publish.state == job.state == CommentJobState.BLOCKED
        assert await enqueue_due_publish_retries(session, now=utc_now() + timedelta(minutes=5)) == []
    assert (await mock_service.get_comments("auto-mode-post", inject_failure=False)).items == []


async def test_quota_reservation_uses_utc_day_with_non_utc_database(clean_database, monkeypatch):
    context = await _ready(clean_database)
    now = utc_now().replace(hour=0, minute=30, second=0, microsecond=0)
    async with clean_database() as session:
        publish = await session.get(PublishJob, context["publish_id"])
        alternative = await session.scalar(select(CommentCandidate).where(CommentCandidate.id != publish.candidate_id))
        account = await session.get(BrandAccount, publish.brand_account_id)
        account.max_comments_per_day = 1
        session.add(PublishJob(
            candidate_id=alternative.id, brand_account_id=publish.brand_account_id,
            platform=publish.platform, mode=publish.mode, idempotency_key=f"utc-test:{uuid4()}",
            state=CommentJobState.PUBLISHING, started_at=now - timedelta(minutes=15),
        ))
        await session.commit()
    monkeypatch.setattr(publisher_runtime, "utc_now", lambda: now)
    async with clean_database() as session:
        if session.bind.dialect.name == "postgresql":
            await session.execute(text("SET LOCAL TIME ZONE 'America/New_York'"))
        with pytest.raises(PermissionError, match="Account daily limit"):
            await publisher_runtime.publish_comment_job(session, context["publish_id"])


async def test_suspended_tenant_token_is_denied_and_invalid_filters_are_422(clean_database):
    context = await _ready(clean_database)
    token = create_access_token(
        subject=context["user_id"], secret=get_settings().app_secret_key.get_secret_value(),
        expires_delta=timedelta(minutes=5),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1",
                                 headers={"Authorization": "Bearer " + token}) as client:
        for path in ("/posts?platform=BOGUS", "/comments/candidates?status=BOGUS",
                     "/comments/published?platform=BOGUS", "/comments/publish-jobs?state=BOGUS",
                     "/review/jobs?status=BOGUS"):
            assert (await client.get(path)).status_code == 422
        async with clean_database() as session:
            tenant = await session.get(Tenant, context["tenant_id"])
            tenant.status = TenantStatus.SUSPENDED
            await session.commit()
        assert (await client.get("/auth/me")).status_code == 403
        assert (await client.post("/brands", json={"name": "Must be blocked"})).status_code == 403
