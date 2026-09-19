"""Capability-gated Douyin adapter skeleton using only an official client port."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ...domain.capabilities import PlatformCapabilities
from ...domain.enums import CapabilityStatus, Platform
from ..base import (
    AuthorizationContext,
    CapabilityName,
    CapabilityRecord,
    CapabilityScope,
    CapabilityUseContext,
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
from ..errors import AuthorizationScopeError, PlatformPermanentError
from .client import DouyinClient

VERIFIED_AT = datetime(2026, 9, 19, tzinfo=timezone.utc)
DOCUMENTATION_SOURCES = [
    "https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/search-video/account-video-list",
    "https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/search-video/video-data/",
    "https://open.douyin.com/platform/resource/docs/openapi/interaction-management/comment-management-user/comment-list",
    "https://open.douyin.com/platform/resource/docs/openapi/interaction-management/comment-management-user/video-comment-reply",
]
OFFICIAL_REQUIRED_SCOPES = {
    CapabilityName.CREATOR_MONITORING: {"video.list"},
    CapabilityName.LATEST_POSTS: {"video.list"},
    CapabilityName.POST_FETCH: {"video.data"},
    CapabilityName.COMMENT_READ: {"item.comment"},
    CapabilityName.COMMENT_REPLY: {"item.comment"},
    CapabilityName.COMMENT_CREATED_AT: {"item.comment"},
}


def douyin_capabilities() -> PlatformCapabilities:
    return PlatformCapabilities(
        creator_monitoring=CapabilityStatus.CONDITIONAL,
        new_post_webhook=CapabilityStatus.UNKNOWN,
        latest_posts=CapabilityStatus.CONDITIONAL,
        post_fetch=CapabilityStatus.CONDITIONAL,
        comment_read=CapabilityStatus.CONDITIONAL,
        top_level_comment=CapabilityStatus.UNKNOWN,
        comment_reply=CapabilityStatus.CONDITIONAL,
        comment_delete=CapabilityStatus.UNKNOWN,
        comment_created_at=CapabilityStatus.CONDITIONAL,
        chronological_rank=CapabilityStatus.UNKNOWN,
        visible_rank=CapabilityStatus.UNKNOWN,
        ai_disclosure=CapabilityStatus.UNKNOWN,
    )


def _creator_id(creator: Any) -> str:
    value = (
        creator.get("external_creator_id")
        if isinstance(creator, dict)
        else getattr(creator, "external_creator_id", None)
    )
    if not value:
        raise PlatformPermanentError(
            "Creator reference is missing external_creator_id", platform="DOUYIN"
        )
    return str(value)


class DouyinAdapter(PlatformAdapter):
    platform = Platform.DOUYIN

    def __init__(
        self,
        client: DouyinClient | None = None,
        *,
        authorization: AuthorizationContext | None = None,
        verified_capabilities: Iterable[CapabilityName | str] = (),
        required_scopes: Mapping[CapabilityName | str, Iterable[str]] | None = None,
    ) -> None:
        self.client = client or DouyinClient()
        binding = authorization or self.client.authorization
        self.authorization = binding.model_copy(deep=True) if binding else None
        self._owned_post_ids: set[str] = set()
        self._verified = {
            item if isinstance(item, CapabilityName) else CapabilityName(str(item).upper())
            for item in verified_capabilities
        }
        scope_map = required_scopes or {}
        self._required_scopes = {
            key if isinstance(key, CapabilityName) else CapabilityName(str(key).upper()): list(
                value
            )
            for key, value in scope_map.items()
        }
        self.capability_records: dict[CapabilityName, CapabilityRecord] = {
            name: CapabilityRecord(
                platform=self.platform,
                capability=name,
                status=CapabilityStatus.CONDITIONAL,
                verified_at=VERIFIED_AT,
                source_title="Platform Capabilities Registry (official-source verification required at deployment)",
                source_owner="Douyin official platform",
                scope=CapabilityScope(
                    authorization_required=True,
                    required_authorization_scopes=sorted(
                        OFFICIAL_REQUIRED_SCOPES[name] | set(self._required_scopes.get(name, []))
                    ),
                    allowed_external_creator_ids=(
                        [self.authorization.external_creator_id]
                        if self.authorization and self.authorization.external_creator_id
                        else []
                    ),
                ),
                limitations=["Only the exact authorized account/content scope may be used"],
            )
            for name in (
                CapabilityName.CREATOR_MONITORING,
                CapabilityName.LATEST_POSTS,
                CapabilityName.POST_FETCH,
                CapabilityName.COMMENT_READ,
                CapabilityName.COMMENT_REPLY,
                CapabilityName.COMMENT_CREATED_AT,
            )
        }

    async def get_capabilities(self) -> PlatformCapabilities:
        return douyin_capabilities()

    async def get_integration_status(self) -> PlatformIntegrationStatus:
        configured = bool(
            self.client.configured and self.authorization == self.client.authorization
        )
        return PlatformIntegrationStatus(
            platform=self.platform,
            configured=configured,
            reason=(
                "TOP_LEVEL_COMMENT_UNVERIFIED"
                if configured
                else "OFFICIAL_INTEGRATION_NOT_CONFIGURED"
            ),
            source_urls=DOCUMENTATION_SOURCES,
        )

    def _context(
        self, capability: CapabilityName, *, external_creator_id: str | None = None
    ) -> CapabilityUseContext:
        auth = self.authorization
        if external_creator_id and (
            auth is None or auth.external_creator_id != external_creator_id
        ):
            raise AuthorizationScopeError(
                "Requested creator does not match the authorized account",
                platform=self.platform.value,
                capability=capability.value,
            )
        return CapabilityUseContext(
            authorization=auth,
            conditions_satisfied=capability in self._verified,
            manual_workflow_available=True,
        )

    async def _require(
        self, capability: CapabilityName, *, external_creator_id: str | None = None
    ) -> None:
        capabilities = await self.get_capabilities()
        require_official_capability(
            capabilities,
            capability,
            platform=self.platform,
            context=self._context(capability, external_creator_id=external_creator_id),
            record=self.capability_records.get(capability),
        )
        self.client.require_authorization(self.authorization)

    def _require_owned_post(self, external_post_id: str) -> None:
        if external_post_id not in self._owned_post_ids:
            raise AuthorizationScopeError(
                "Post ownership must first be verified by authorized latest-post discovery",
                platform=self.platform.value,
            )

    def _validate_post_owner(self, post: PlatformPost) -> None:
        if self.authorization is None or (
            post.external_creator_id != self.authorization.external_creator_id
        ):
            raise AuthorizationScopeError(
                "Official response contains a post outside the authorized creator scope",
                platform=self.platform.value,
            )

    async def get_latest_posts(self, creator: Any, cursor: str | None = None) -> PostPage:
        external_creator_id = _creator_id(creator)
        await self._require(CapabilityName.LATEST_POSTS, external_creator_id=external_creator_id)
        page = await self.client.get_latest_posts(external_creator_id, cursor, str(uuid4()))
        for post in page.items:
            self._validate_post_owner(post)
        self._owned_post_ids.update(post.external_post_id for post in page.items)
        return page

    async def get_post(self, external_post_id: str) -> PlatformPost:
        await self._require(CapabilityName.POST_FETCH)
        self._require_owned_post(external_post_id)
        post = await self.client.get_post(external_post_id, str(uuid4()))
        self._validate_post_owner(post)
        if post.external_post_id != external_post_id:
            raise PlatformPermanentError(
                "Official response returned a different post", platform="DOUYIN"
            )
        return post

    async def get_comments(self, external_post_id: str, cursor: str | None = None) -> CommentPage:
        await self._require(CapabilityName.COMMENT_READ)
        self._require_owned_post(external_post_id)
        page = await self.client.get_comments(external_post_id, cursor, str(uuid4()))
        if any(item.external_post_id != external_post_id for item in page.items):
            raise PlatformPermanentError(
                "Official response returned comments for another post", platform="DOUYIN"
            )
        return page

    async def publish_top_level_comment(self, request: PublishCommentRequest) -> PublishReceipt:
        # This is deliberately UNKNOWN even though reply may be conditionally available.
        await self._require(CapabilityName.TOP_LEVEL_COMMENT)
        raise AssertionError("unreachable: UNKNOWN capability must fail before an external call")

    async def reply_comment(self, request: ReplyCommentRequest) -> PublishReceipt:
        await self._require(CapabilityName.COMMENT_REPLY)
        self._require_owned_post(request.external_post_id)
        return await self.client.reply_comment(request)

    async def reconcile_publish(self, request: ReconcileRequest) -> ReconcileResult:
        await self._require(CapabilityName.COMMENT_READ)
        self._require_owned_post(request.external_post_id)
        return await self.client.reconcile_publish(request)


__all__ = ["DouyinAdapter", "douyin_capabilities"]
