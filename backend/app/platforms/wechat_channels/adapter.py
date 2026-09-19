"""Fail-safe WeChat Channels adapter skeleton."""

from __future__ import annotations

from typing import Any

from ...domain.capabilities import PlatformCapabilities
from ...domain.enums import CapabilityStatus, Platform
from ..base import (
    CapabilityName,
    CommentPage,
    PlatformAdapter,
    PlatformPost,
    PostPage,
    PublishCommentRequest,
    PublishReceipt,
    ReconcileRequest,
    ReconcileResult,
    ReplyCommentRequest,
    require_official_capability,
)


def wechat_channels_capabilities() -> PlatformCapabilities:
    return PlatformCapabilities(
        creator_monitoring=CapabilityStatus.UNKNOWN,
        new_post_webhook=CapabilityStatus.UNKNOWN,
        latest_posts=CapabilityStatus.UNKNOWN,
        post_fetch=CapabilityStatus.UNKNOWN,
        comment_read=CapabilityStatus.UNKNOWN,
        top_level_comment=CapabilityStatus.UNKNOWN,
        comment_reply=CapabilityStatus.UNKNOWN,
        comment_delete=CapabilityStatus.UNKNOWN,
        comment_created_at=CapabilityStatus.UNKNOWN,
        chronological_rank=CapabilityStatus.UNKNOWN,
        visible_rank=CapabilityStatus.UNKNOWN,
        ai_disclosure=CapabilityStatus.UNKNOWN,
    )


class WechatChannelsAdapter(PlatformAdapter):
    platform = Platform.WECHAT_CHANNELS

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self.external_call_count = 0

    async def get_capabilities(self) -> PlatformCapabilities:
        return wechat_channels_capabilities()

    async def _deny(self, capability: CapabilityName) -> None:
        require_official_capability(
            await self.get_capabilities(),
            capability,
            platform=self.platform,
        )
        raise AssertionError("unreachable: UNKNOWN capability must fail closed")

    async def get_latest_posts(self, creator: Any, cursor: str | None = None) -> PostPage:
        await self._deny(CapabilityName.LATEST_POSTS)
        raise AssertionError("unreachable")

    async def get_post(self, external_post_id: str) -> PlatformPost:
        await self._deny(CapabilityName.POST_FETCH)
        raise AssertionError("unreachable")

    async def get_comments(self, external_post_id: str, cursor: str | None = None) -> CommentPage:
        await self._deny(CapabilityName.COMMENT_READ)
        raise AssertionError("unreachable")

    async def publish_top_level_comment(self, request: PublishCommentRequest) -> PublishReceipt:
        await self._deny(CapabilityName.TOP_LEVEL_COMMENT)
        raise AssertionError("unreachable")

    async def reply_comment(self, request: ReplyCommentRequest) -> PublishReceipt:
        await self._deny(CapabilityName.COMMENT_REPLY)
        raise AssertionError("unreachable")

    async def reconcile_publish(self, request: ReconcileRequest) -> ReconcileResult:
        await self._deny(CapabilityName.COMMENT_READ)
        raise AssertionError("unreachable")


# Both spellings are exported because the product enum uses WECHAT_CHANNELS while
# some callers naturally title-case "WeChat".
WeChatChannelsAdapter = WechatChannelsAdapter


__all__ = [
    "WeChatChannelsAdapter",
    "WechatChannelsAdapter",
    "wechat_channels_capabilities",
]
