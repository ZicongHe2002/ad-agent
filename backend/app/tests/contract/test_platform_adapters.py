from __future__ import annotations

import inspect

import pytest

from app.domain.capabilities import PlatformCapabilities
from app.domain.enums import CapabilityStatus
from app.platforms.base import PublishCommentRequest, ReplyCommentRequest
from app.platforms.douyin.adapter import DouyinAdapter
from app.platforms.errors import UnknownCapabilityError, UnsupportedCapabilityError
from app.platforms.mock.adapter import MockPlatformAdapter
from app.platforms.mock.service import MockPlatformService
from app.platforms.wechat_channels.adapter import WechatChannelsAdapter
from app.platforms.xiaohongshu.adapter import XiaohongshuAdapter


@pytest.mark.parametrize(
    "adapter",
    [MockPlatformAdapter(), DouyinAdapter(), XiaohongshuAdapter(), WechatChannelsAdapter()],
)
async def test_capability_contract_is_complete(adapter) -> None:
    capabilities = await adapter.get_capabilities()
    assert isinstance(capabilities, PlatformCapabilities)
    assert set(capabilities.model_dump()) == set(PlatformCapabilities.model_fields)


@pytest.mark.parametrize("adapter", [XiaohongshuAdapter(), WechatChannelsAdapter()])
async def test_unverified_real_adapters_fail_closed(adapter) -> None:
    with pytest.raises((UnknownCapabilityError, UnsupportedCapabilityError)):
        await adapter.publish_top_level_comment(
            PublishCommentRequest(
                external_post_id="post",
                text="context grounded",
                account_id="account",
                idempotency_key="key",
            )
        )


async def test_reply_capability_never_grants_top_level_publish() -> None:
    service = MockPlatformService()
    creator = await service.create_creator("creator")
    post = await service.create_post(creator.external_creator_id)
    service.configure_capabilities(
        top_level_comment=CapabilityStatus.UNKNOWN,
        comment_reply=CapabilityStatus.SUPPORTED,
    )
    adapter = MockPlatformAdapter(service)
    with pytest.raises(UnknownCapabilityError):
        await adapter.publish_top_level_comment(
            PublishCommentRequest(
                external_post_id=post.external_post_id,
                text="specific comment",
                account_id="account",
                idempotency_key="top-level",
            )
        )
    # The distinct reply operation still checks and uses its own capability.
    parent = await service.simulate_comments(post.external_post_id, 1)
    receipt = await adapter.reply_comment(
        ReplyCommentRequest(
            external_post_id=post.external_post_id,
            parent_comment_id=parent[0].external_comment_id,
            text="specific reply",
            account_id="account",
            idempotency_key="reply",
        )
    )
    assert receipt.external_comment_id


def test_real_adapters_contain_no_browser_automation_fallback() -> None:
    source = "\n".join(
        inspect.getsource(adapter_type)
        for adapter_type in (DouyinAdapter, XiaohongshuAdapter, WechatChannelsAdapter)
    ).lower()
    for forbidden in ("selenium", "playwright", "captcha", "device fingerprint", "private api"):
        assert forbidden not in source
