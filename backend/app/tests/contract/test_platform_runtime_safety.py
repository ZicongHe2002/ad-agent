from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.domain.enums import CapabilityName, CapabilityStatus, Platform
from app.platforms.base import (
    AuthorizationContext,
    PlatformPost,
    PostPage,
    PublishCommentRequest,
    PublishReceipt,
    ReconcileRequest,
    ReconcileResult,
    ReplyCommentRequest,
    utc_now,
)
from app.platforms.douyin.adapter import DouyinAdapter
from app.platforms.douyin.client import DouyinClient
from app.platforms.errors import (
    AuthorizationExpiredError,
    AuthorizationScopeError,
    PlatformIntegrationNotConfiguredError,
    PlatformTemporaryError,
    PlatformTimeoutError,
    PublishUncertainError,
    UnknownCapabilityError,
)
from app.platforms.mock.failure_injection import MockFailureProfile
from app.platforms.mock.persistent_service import PersistentMockPlatformService
from app.platforms.mock.service import MockPlatformService
from app.platforms.runtime import build_platform_registry, platform_integration_statuses


def _binding(**overrides):
    return AuthorizationContext(
        **{
            "authorization_id": "authorization-a",
            "account_id": "account-a",
            "external_creator_id": "creator-a",
            "granted_scopes": {"video.list", "video.data", "item.comment"},
            "expires_at": utc_now() + timedelta(hours=1),
            **overrides,
        }
    )


def _adapter(**authorization_overrides):
    auth = _binding(**authorization_overrides)
    transport = SimpleNamespace(
        get_latest_posts=AsyncMock(
            return_value=PostPage(
                items=[
                    PlatformPost(
                        external_post_id="post-a",
                        external_creator_id="creator-a",
                        published_at=utc_now(),
                    )
                ]
            )
        ),
        get_post=AsyncMock(),
        get_comments=AsyncMock(),
        reply_comment=AsyncMock(),
        reconcile_publish=AsyncMock(),
    )
    adapter = DouyinAdapter(
        DouyinClient(transport, authorization=auth),
        verified_capabilities=list(CapabilityName),
    )
    return adapter, transport


def _reply(account_id="account-a"):
    return ReplyCommentRequest(
        external_post_id="post-a",
        account_id=account_id,
        text="Specific reply",
        parent_comment_id="parent-a",
        idempotency_key="intent-a",
    )


async def test_integration_status_does_not_claim_real_publish_support():
    service = MockPlatformService()
    registry = build_platform_registry(mock_service=service)
    states = {item.platform: item for item in await platform_integration_statuses(registry)}
    assert states[Platform.MOCK].configured
    assert states[Platform.MOCK].top_level_publish_configured
    for platform in (Platform.DOUYIN, Platform.XIAOHONGSHU, Platform.WECHAT_CHANNELS):
        assert not states[platform].configured
        assert not states[platform].top_level_publish_configured
    service.configure_capabilities(top_level_comment=CapabilityStatus.DISABLED)
    assert not (
        await registry.get(Platform.MOCK).get_integration_status()
    ).top_level_publish_configured


async def test_douyin_binding_cannot_authorize_another_creator():
    adapter, transport = _adapter()
    with pytest.raises(AuthorizationScopeError):
        await adapter.get_latest_posts({"external_creator_id": "creator-b"})
    transport.get_latest_posts.assert_not_called()
    await adapter.get_latest_posts({"external_creator_id": "creator-a"})
    transport.get_latest_posts.assert_awaited_once()


async def test_douyin_does_not_infer_missing_creator_from_request():
    adapter, transport = _adapter(external_creator_id=None)
    with pytest.raises(AuthorizationScopeError):
        await adapter.get_latest_posts({"external_creator_id": "creator-a"})
    transport.get_latest_posts.assert_not_called()


async def test_douyin_adapter_cannot_switch_bound_client_to_another_account():
    adapter, transport = _adapter()
    adapter.authorization = _binding(account_id="account-b")
    with pytest.raises(AuthorizationScopeError):
        await adapter.get_latest_posts({"external_creator_id": "creator-a"})
    assert not (await adapter.get_integration_status()).configured
    transport.get_latest_posts.assert_not_called()


async def test_douyin_requires_credential_binding_and_unexpired_authorization():
    transport = SimpleNamespace(get_latest_posts=AsyncMock())
    with pytest.raises(PlatformIntegrationNotConfiguredError):
        await DouyinClient(transport).get_latest_posts("creator-a", None, "trace")
    expired = DouyinClient(
        transport, authorization=_binding(expires_at=utc_now() - timedelta(seconds=1))
    )
    with pytest.raises(AuthorizationExpiredError):
        await expired.get_latest_posts("creator-a", None, "trace")
    transport.get_latest_posts.assert_not_called()


async def test_douyin_requires_official_scope_even_with_verified_flag():
    adapter, transport = _adapter(granted_scopes={"video.list"})
    await adapter.get_latest_posts({"external_creator_id": "creator-a"})
    with pytest.raises(AuthorizationScopeError):
        await adapter.reply_comment(_reply())
    transport.reply_comment.assert_not_called()


async def test_douyin_rejects_unverified_post_before_external_call():
    adapter, transport = _adapter()
    with pytest.raises(AuthorizationScopeError):
        await adapter.get_post("post-b")
    with pytest.raises(AuthorizationScopeError):
        await adapter.reply_comment(_reply())
    transport.get_post.assert_not_called()
    transport.reply_comment.assert_not_called()


async def test_douyin_discovery_cannot_poison_owned_post_scope():
    adapter, transport = _adapter()
    transport.get_latest_posts.return_value = PostPage(
        items=[
            PlatformPost(
                external_post_id="post-a", external_creator_id="creator-b", published_at=utc_now()
            )
        ]
    )
    with pytest.raises(AuthorizationScopeError):
        await adapter.get_latest_posts({"external_creator_id": "creator-a"})
    with pytest.raises(AuthorizationScopeError):
        await adapter.reply_comment(_reply())
    transport.reply_comment.assert_not_called()


async def test_douyin_reply_and_reconciliation_cannot_use_another_account():
    adapter, transport = _adapter()
    await adapter.get_latest_posts({"external_creator_id": "creator-a"})
    with pytest.raises(AuthorizationScopeError):
        await adapter.reply_comment(_reply("account-b"))
    with pytest.raises(AuthorizationScopeError):
        await adapter.reconcile_publish(
            ReconcileRequest(
                external_post_id="post-a", account_id="account-b", idempotency_key="intent-a"
            )
        )
    transport.reply_comment.assert_not_called()
    transport.reconcile_publish.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("response lost"), PlatformTimeoutError(), RuntimeError("SDK disconnected")],
)
async def test_douyin_reply_receipt_and_timeout_are_not_false_success(failure):
    adapter, transport = _adapter()
    await adapter.get_latest_posts({"external_creator_id": "creator-a"})
    receipt = PublishReceipt(
        external_comment_id="comment-a",
        external_post_id="post-a",
        created_at=utc_now(),
        idempotency_key="intent-a",
    )
    transport.reply_comment.return_value = receipt
    assert await adapter.reply_comment(_reply()) == receipt
    transport.reply_comment.side_effect = failure
    with pytest.raises(PublishUncertainError) as error:
        await adapter.reply_comment(_reply())
    assert error.value.idempotency_key == "intent-a"
    assert transport.reply_comment.await_count == 2


async def test_douyin_reconciliation_rejects_receipt_for_another_intent():
    adapter, transport = _adapter()
    await adapter.get_latest_posts({"external_creator_id": "creator-a"})
    transport.reconcile_publish.return_value = ReconcileResult(
        found=True,
        status="PUBLISHED",
        receipt=PublishReceipt(
            external_comment_id="comment-b",
            external_post_id="post-a",
            created_at=utc_now(),
            idempotency_key="another-intent",
        ),
    )
    with pytest.raises(PlatformTemporaryError):
        await adapter.reconcile_publish(
            ReconcileRequest(
                external_post_id="post-a", account_id="account-a", idempotency_key="intent-a"
            )
        )


async def test_configured_douyin_client_never_implies_top_level_capability():
    adapter, transport = _adapter()
    state = await adapter.get_integration_status()
    assert state.configured and not state.top_level_publish_configured
    with pytest.raises(UnknownCapabilityError):
        await adapter.publish_top_level_comment(
            PublishCommentRequest(
                external_post_id="post-a",
                account_id="account-a",
                text="Specific observation",
                idempotency_key="top-level",
            )
        )
    transport.reply_comment.assert_not_called()


async def test_persisted_mock_preserves_seeded_failure_sequence_across_requests():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        persistent = PersistentMockPlatformService(
            async_sessionmaker(engine, expire_on_commit=False)
        )
        profile = MockFailureProfile(timeout_rate=0.5, seed=0)
        await persistent.configure_failure_profile(profile)
        memory = MockPlatformService(failure_profile=profile)
        outcomes = []
        for service in (persistent, memory):
            await service.create_creator("Creator", external_creator_id="creator")
            result = []
            for _ in range(10):
                try:
                    await service.get_latest_posts("creator")
                    result.append("OK")
                except PlatformTimeoutError:
                    result.append("TIMEOUT")
            outcomes.append(result)
        assert outcomes[0] == outcomes[1]
        assert set(outcomes[0]) == {"OK", "TIMEOUT"}
        await persistent.configure_failure_profile(MockFailureProfile(timeout_rate=1))
        with pytest.raises(PlatformTimeoutError):
            await persistent.get_latest_posts("creator")
    finally:
        await engine.dispose()
