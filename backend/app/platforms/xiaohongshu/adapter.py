"""Fail-safe Xiaohongshu adapter skeleton.

No social operation is verified, so every contract method is capability-gated and
fails before any injected client can be touched.
"""

from __future__ import annotations

from typing import Any

from ...domain.capabilities import PlatformCapabilities
from ...domain.enums import CapabilityStatus, Platform
from ..base import (
    CapabilityName,
    CommentPage,
    PlatformAdapter,
    PlatformIntegrationStatus,
    PlatformPost,
    PostPage,
    PublishCommentRequest,
    PublishReceipt,
    ReconcileRequest,
    ReconcileResult,
    ReplyCommentRequest,
    require_official_capability,
)


def xiaohongshu_capabilities() -> PlatformCapabilities:
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


class XiaohongshuAdapter(PlatformAdapter):
    platform = Platform.XIAOHONGSHU

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self.external_call_count = 0

    async def get_capabilities(self) -> PlatformCapabilities:
        return xiaohongshu_capabilities()

    async def get_integration_status(self) -> PlatformIntegrationStatus:
        return PlatformIntegrationStatus(
            platform=self.platform,
            reason="TOP_LEVEL_COMMENT_UNVERIFIED",
            source_urls=["https://openaccount.xiaohongshu.com/docs/scope"],
        )

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


__all__ = ["XiaohongshuAdapter", "xiaohongshu_capabilities"]
