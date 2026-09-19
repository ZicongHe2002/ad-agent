"""PlatformAdapter implementation backed by :class:`MockPlatformService`."""

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
from ..errors import PlatformPermanentError
from .persistent_service import PersistentMockPlatformService
from .service import MockPlatformService


def _creator_id(creator: Any) -> str:
    if isinstance(creator, str):
        return creator
    if isinstance(creator, dict):
        value = creator.get("external_creator_id")
    else:
        value = getattr(creator, "external_creator_id", None)
    if not value:
        raise PlatformPermanentError(
            "Creator reference is missing external_creator_id",
            platform=Platform.MOCK.value,
        )
    return str(value)


class MockPlatformAdapter(PlatformAdapter):
    platform = Platform.MOCK

    def __init__(
        self,
        service: MockPlatformService | PersistentMockPlatformService | None = None,
    ) -> None:
        self.service = service or MockPlatformService()

    async def get_capabilities(self) -> PlatformCapabilities:
        if isinstance(self.service, PersistentMockPlatformService):
            return await self.service.get_capabilities()
        return self.service.capabilities

    async def get_integration_status(self) -> PlatformIntegrationStatus:
        capabilities = await self.get_capabilities()
        return PlatformIntegrationStatus(
            platform=self.platform,
            configured=True,
            top_level_publish_configured=(
                capabilities.top_level_comment == CapabilityStatus.SUPPORTED
            ),
            reason="MOCK_CONFIGURED",
        )

    async def get_latest_posts(self, creator: Any, cursor: str | None = None) -> PostPage:
        capabilities = await self.get_capabilities()
        require_official_capability(
            capabilities, CapabilityName.LATEST_POSTS, platform=self.platform
        )
        return await self.service.get_latest_posts(_creator_id(creator), cursor)

    async def get_post(self, external_post_id: str) -> PlatformPost:
        capabilities = await self.get_capabilities()
        require_official_capability(capabilities, CapabilityName.POST_FETCH, platform=self.platform)
        return await self.service.get_post(external_post_id)

    async def get_comments(self, external_post_id: str, cursor: str | None = None) -> CommentPage:
        capabilities = await self.get_capabilities()
        require_official_capability(
            capabilities, CapabilityName.COMMENT_READ, platform=self.platform
        )
        return await self.service.get_comments(external_post_id, cursor)

    async def publish_top_level_comment(self, request: PublishCommentRequest) -> PublishReceipt:
        capabilities = await self.get_capabilities()
        # Deliberately check TOP_LEVEL_COMMENT.  COMMENT_REPLY is never a fallback.
        require_official_capability(
            capabilities, CapabilityName.TOP_LEVEL_COMMENT, platform=self.platform
        )
        return await self.service.publish_top_level_comment(request)

    async def reply_comment(self, request: ReplyCommentRequest) -> PublishReceipt:
        capabilities = await self.get_capabilities()
        require_official_capability(
            capabilities, CapabilityName.COMMENT_REPLY, platform=self.platform
        )
        return await self.service.reply_comment(request)

    async def reconcile_publish(self, request: ReconcileRequest) -> ReconcileResult:
        capabilities = await self.get_capabilities()
        require_official_capability(
            capabilities, CapabilityName.COMMENT_READ, platform=self.platform
        )
        return await self.service.reconcile_publish(request)


__all__ = ["MockPlatformAdapter"]
