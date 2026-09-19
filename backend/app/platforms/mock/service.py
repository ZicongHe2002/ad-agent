"""In-memory, deterministic implementation of the complete mock platform."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ...domain.capabilities import PlatformCapabilities
from ...domain.enums import CapabilityStatus
from ..base import (
    CommentPage,
    PlatformComment,
    PlatformPost,
    PostPage,
    PublishCommentRequest,
    PublishReceipt,
    ReconcileRequest,
    ReconcileResult,
    ReplyCommentRequest,
    utc_now,
)
from ..errors import IdempotencyConflictError, PlatformPermanentError
from .failure_injection import FailureInjector, MockFailureProfile
from .ranking import (
    VisibleRankingStrategy,
    chronological_rank,
    visible_comments,
    visible_rank,
)


class MockCreator(BaseModel):
    external_creator_id: str
    name: str
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MockPost(PlatformPost):
    created_at: datetime = Field(default_factory=utc_now)


class MockComment(PlatformComment):
    idempotency_key: str | None = None
    account_id: str | None = None


class MockPlatformPolicy(BaseModel):
    visible_ranking: VisibleRankingStrategy = VisibleRankingStrategy.CHRONOLOGICAL
    ranking_seed: str = "firstcomment-mock"
    page_size: int = Field(default=50, ge=1, le=500)
    max_comment_length: int = Field(default=500, ge=1, le=10_000)


def supported_capabilities() -> PlatformCapabilities:
    values = {
        "creator_monitoring": CapabilityStatus.SUPPORTED,
        "new_post_webhook": CapabilityStatus.SUPPORTED,
        "latest_posts": CapabilityStatus.SUPPORTED,
        "post_fetch": CapabilityStatus.SUPPORTED,
        "comment_read": CapabilityStatus.SUPPORTED,
        "top_level_comment": CapabilityStatus.SUPPORTED,
        "comment_reply": CapabilityStatus.SUPPORTED,
        "comment_delete": CapabilityStatus.SUPPORTED,
        "comment_created_at": CapabilityStatus.SUPPORTED,
        "chronological_rank": CapabilityStatus.SUPPORTED,
        "visible_rank": CapabilityStatus.SUPPORTED,
        "ai_disclosure": CapabilityStatus.SUPPORTED,
    }
    return PlatformCapabilities(**values)


def _offset(cursor: str | None) -> int:
    if cursor is None or cursor == "":
        return 0
    try:
        value = int(cursor)
    except (TypeError, ValueError) as exc:
        raise PlatformPermanentError("Invalid pagination cursor", platform="MOCK") from exc
    if value < 0:
        raise PlatformPermanentError("Invalid pagination cursor", platform="MOCK")
    return value


def _page(items: Sequence[Any], cursor: str | None, page_size: int) -> tuple[list[Any], str | None]:
    start = _offset(cursor)
    result = list(items[start : start + page_size])
    following = start + len(result)
    return result, str(following) if following < len(items) else None


class MockPlatformService:
    """Thread-safe state store used by both API handlers and the adapter."""

    def __init__(
        self,
        *,
        policy: MockPlatformPolicy | None = None,
        failure_profile: MockFailureProfile | None = None,
    ) -> None:
        self.policy = policy or MockPlatformPolicy()
        self.failures = FailureInjector(failure_profile)
        self.capabilities = supported_capabilities()
        self._creators: dict[str, MockCreator] = {}
        self._posts: dict[str, MockPost] = {}
        self._comments: dict[str, MockComment] = {}
        self._post_comment_ids: dict[str, list[str]] = {}
        self._idempotency: dict[str, tuple[str, str]] = {}
        self._lock = asyncio.Lock()

    async def reset(self) -> None:
        async with self._lock:
            self._creators.clear()
            self._posts.clear()
            self._comments.clear()
            self._post_comment_ids.clear()
            self._idempotency.clear()
            self.capabilities = supported_capabilities()
            self.policy = MockPlatformPolicy()
            self.failures.reset()

    def configure_failure_profile(
        self, profile: MockFailureProfile | Mapping[str, Any]
    ) -> MockFailureProfile:
        parsed = (
            profile
            if isinstance(profile, MockFailureProfile)
            else MockFailureProfile(**dict(profile))
        )
        return self.failures.configure(parsed)

    def configure_capabilities(self, **statuses: CapabilityStatus | str) -> PlatformCapabilities:
        current = (
            self.capabilities.model_dump()
            if hasattr(self.capabilities, "model_dump")
            else self.capabilities.dict()
        )
        unknown = set(statuses) - set(current)
        if unknown:
            raise ValueError(f"Unknown capability fields: {', '.join(sorted(unknown))}")
        current.update(statuses)
        self.capabilities = PlatformCapabilities(**current)
        return self.capabilities

    def configure_policy(
        self, policy: MockPlatformPolicy | Mapping[str, Any]
    ) -> MockPlatformPolicy:
        self.policy = (
            policy if isinstance(policy, MockPlatformPolicy) else MockPlatformPolicy(**dict(policy))
        )
        return self.policy

    async def create_creator(
        self,
        name: str,
        *,
        external_creator_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MockCreator:
        creator_id = external_creator_id or f"mock-creator-{uuid4()}"
        async with self._lock:
            if creator_id in self._creators:
                raise PlatformPermanentError("Mock creator already exists", platform="MOCK")
            creator = MockCreator(
                external_creator_id=creator_id, name=name, metadata=dict(metadata or {})
            )
            self._creators[creator_id] = creator
            return creator

    async def list_creators(self) -> list[MockCreator]:
        async with self._lock:
            return sorted(
                self._creators.values(),
                key=lambda item: (item.created_at, item.external_creator_id),
            )

    async def get_creator(self, external_creator_id: str) -> MockCreator:
        async with self._lock:
            try:
                return self._creators[external_creator_id]
            except KeyError as exc:
                raise PlatformPermanentError("Mock creator not found", platform="MOCK") from exc

    async def create_post(
        self,
        external_creator_id: str,
        *,
        external_post_id: str | None = None,
        published_at: datetime | None = None,
        title: str | None = None,
        caption: str | None = None,
        hashtags: Sequence[str] | None = None,
        mentions: Sequence[str] | None = None,
        media_urls: Sequence[str] | None = None,
        raw_payload: Mapping[str, Any] | None = None,
    ) -> MockPost:
        post_id = external_post_id or f"mock-post-{uuid4()}"
        async with self._lock:
            if external_creator_id not in self._creators:
                raise PlatformPermanentError("Mock creator not found", platform="MOCK")
            if post_id in self._posts:
                raise PlatformPermanentError("Mock post already exists", platform="MOCK")
            post = MockPost(
                external_post_id=post_id,
                external_creator_id=external_creator_id,
                published_at=published_at or utc_now(),
                title=title,
                caption=caption,
                hashtags=list(hashtags or ()),
                mentions=list(mentions or ()),
                media_urls=list(media_urls or ()),
                raw_payload=dict(raw_payload or {}),
            )
            self._posts[post_id] = post
            self._post_comment_ids[post_id] = []
            return post

    async def get_latest_posts(
        self,
        external_creator_id: str,
        cursor: str | None = None,
        *,
        inject_failure: bool = True,
    ) -> PostPage:
        if inject_failure:
            await self.failures.before_request("get_latest_posts")
        async with self._lock:
            if external_creator_id not in self._creators:
                raise PlatformPermanentError("Mock creator not found", platform="MOCK")
            ordered = sorted(
                (
                    post
                    for post in self._posts.values()
                    if post.external_creator_id == external_creator_id
                ),
                key=lambda item: (item.published_at, item.external_post_id),
                reverse=True,
            )
            items, next_cursor = _page(ordered, cursor, self.policy.page_size)
            return PostPage(items=items, next_cursor=next_cursor)

    async def get_post(self, external_post_id: str, *, inject_failure: bool = True) -> MockPost:
        if inject_failure:
            await self.failures.before_request("get_post")
        async with self._lock:
            try:
                return self._posts[external_post_id]
            except KeyError as exc:
                raise PlatformPermanentError("Mock post not found", platform="MOCK") from exc

    async def _create_comment(
        self,
        *,
        external_post_id: str,
        text: str,
        author_external_id: str | None,
        parent_comment_id: str | None,
        idempotency_key: str | None,
        account_id: str | None,
        created_at: datetime | None = None,
        like_count: int = 0,
        author_pinned: bool = False,
        raw_payload: Mapping[str, Any] | None = None,
    ) -> tuple[MockComment, bool]:
        if not text.strip():
            raise PlatformPermanentError("Comment cannot be empty", platform="MOCK")
        if len(text) > self.policy.max_comment_length:
            raise PlatformPermanentError(
                "Comment exceeds mock platform length limit", platform="MOCK"
            )
        async with self._lock:
            if external_post_id not in self._posts:
                raise PlatformPermanentError("Mock post not found", platform="MOCK")
            if parent_comment_id:
                parent = self._comments.get(parent_comment_id)
                if parent is None or parent.external_post_id != external_post_id:
                    raise PlatformPermanentError(
                        "Parent comment not found on target post", platform="MOCK"
                    )
            fingerprint = (
                f"{external_post_id}\x1f{account_id or ''}\x1f{text}\x1f{parent_comment_id or ''}"
            )
            if idempotency_key and idempotency_key in self._idempotency:
                existing_id, existing_fingerprint = self._idempotency[idempotency_key]
                if existing_fingerprint != fingerprint:
                    raise IdempotencyConflictError(
                        "Idempotency key was already used for different content",
                        platform="MOCK",
                        details={"idempotency_key": idempotency_key},
                    )
                return self._comments[existing_id], False
            timestamp = created_at or utc_now()
            visible_at = timestamp + timedelta(
                milliseconds=self.failures.profile.visibility_delay_ms
            )
            comment = MockComment(
                external_comment_id=f"mock-comment-{uuid4()}",
                external_post_id=external_post_id,
                text=text,
                created_at=timestamp,
                author_external_id=author_external_id,
                parent_comment_id=parent_comment_id,
                like_count=max(0, like_count),
                author_pinned=author_pinned,
                visible_at=visible_at,
                raw_payload=dict(raw_payload or {}),
                idempotency_key=idempotency_key,
                account_id=account_id,
            )
            self._comments[comment.external_comment_id] = comment
            self._post_comment_ids[external_post_id].append(comment.external_comment_id)
            if idempotency_key:
                self._idempotency[idempotency_key] = (comment.external_comment_id, fingerprint)
            return comment, True

    @staticmethod
    def _receipt(comment: MockComment) -> PublishReceipt:
        return PublishReceipt(
            external_comment_id=comment.external_comment_id,
            external_post_id=comment.external_post_id,
            created_at=comment.created_at,
            idempotency_key=comment.idempotency_key or "",
            visible_at=comment.visible_at,
            raw_payload={"mock": True, "parent_comment_id": comment.parent_comment_id},
        )

    async def publish_top_level_comment(self, request: PublishCommentRequest) -> PublishReceipt:
        await self.failures.before_request("publish_top_level_comment")
        comment, created = await self._create_comment(
            external_post_id=request.external_post_id,
            text=request.text,
            author_external_id=request.account_id,
            parent_comment_id=None,
            idempotency_key=request.idempotency_key,
            account_id=request.account_id,
            raw_payload=request.metadata,
        )
        receipt = self._receipt(comment)
        if created:
            self.failures.after_publish(idempotency_key=request.idempotency_key)
        return receipt

    async def reply_comment(self, request: ReplyCommentRequest) -> PublishReceipt:
        await self.failures.before_request("reply_comment")
        comment, created = await self._create_comment(
            external_post_id=request.external_post_id,
            text=request.text,
            author_external_id=request.account_id,
            parent_comment_id=request.parent_comment_id,
            idempotency_key=request.idempotency_key,
            account_id=request.account_id,
            raw_payload=request.metadata,
        )
        receipt = self._receipt(comment)
        if created:
            self.failures.after_publish(idempotency_key=request.idempotency_key)
        return receipt

    async def simulate_comments(
        self,
        external_post_id: str,
        count: int,
        *,
        start_at: datetime | None = None,
        interval_ms: int = 1,
        texts: Sequence[str] | None = None,
    ) -> list[MockComment]:
        if count < 0:
            raise ValueError("count must be non-negative")
        base = start_at or utc_now()
        result: list[MockComment] = []
        for index in range(count):
            text = (
                texts[index]
                if texts is not None and index < len(texts)
                else f"Simulated comment {index + 1}"
            )
            comment, _ = await self._create_comment(
                external_post_id=external_post_id,
                text=text,
                author_external_id=f"simulated-user-{index + 1}",
                parent_comment_id=None,
                idempotency_key=None,
                account_id=None,
                created_at=base + timedelta(milliseconds=index * interval_ms),
                like_count=index,
            )
            result.append(comment)
        return result

    async def get_comments(
        self,
        external_post_id: str,
        cursor: str | None = None,
        *,
        visible_only: bool = True,
        top_level_only: bool = False,
        order: str = "chronological",
        viewer_id: str = "default",
        inject_failure: bool = True,
    ) -> CommentPage:
        if inject_failure:
            await self.failures.before_request("get_comments")
        async with self._lock:
            if external_post_id not in self._posts:
                raise PlatformPermanentError("Mock post not found", platform="MOCK")
            now = utc_now()
            items = [
                self._comments[item_id] for item_id in self._post_comment_ids[external_post_id]
            ]
            if visible_only:
                items = [
                    item for item in items if item.visible_at is None or item.visible_at <= now
                ]
            if top_level_only:
                items = [item for item in items if item.parent_comment_id is None]
            if order.lower() == "visible":
                items = visible_comments(
                    items,
                    self.policy.visible_ranking,
                    seed=f"{self.policy.ranking_seed}:{external_post_id}",
                    viewer_id=viewer_id,
                )
            else:
                items = sorted(items, key=lambda item: (item.created_at, item.external_comment_id))
            page, next_cursor = _page(items, cursor, self.policy.page_size)
            return CommentPage(items=page, next_cursor=next_cursor)

    async def comment_ranks(
        self,
        external_post_id: str,
        external_comment_id: str,
        *,
        viewer_id: str = "default",
    ) -> tuple[int, int]:
        page = await self.get_comments(
            external_post_id,
            visible_only=True,
            top_level_only=True,
            inject_failure=False,
        )
        all_items: list[PlatformComment] = page.items
        # Ranking calls are expected to be exact; bypass configured pagination.
        async with self._lock:
            now = utc_now()
            all_items = []
            for item_id in self._post_comment_ids.get(external_post_id, []):
                comment = self._comments[item_id]
                visible_at = comment.visible_at
                if comment.parent_comment_id is None and (
                    visible_at is None or visible_at <= now
                ):
                    all_items.append(comment)
        chronological = chronological_rank(all_items, external_comment_id)
        visible = visible_rank(
            all_items,
            external_comment_id,
            self.policy.visible_ranking,
            seed=f"{self.policy.ranking_seed}:{external_post_id}",
            viewer_id=viewer_id,
        )
        return chronological, visible

    async def reconcile_publish(self, request: ReconcileRequest) -> ReconcileResult:
        await self.failures.before_request("reconcile_publish")
        async with self._lock:
            item = self._idempotency.get(request.idempotency_key)
            if item is None:
                return ReconcileResult(found=False, status="NOT_FOUND")
            comment = self._comments[item[0]]
            if (
                comment.external_post_id != request.external_post_id
                or comment.account_id != request.account_id
            ):
                return ReconcileResult(found=False, status="NOT_FOUND")
            return ReconcileResult(found=True, status="PUBLISHED", receipt=self._receipt(comment))


__all__ = [
    "MockComment",
    "MockCreator",
    "MockPlatformPolicy",
    "MockPlatformService",
    "MockPost",
    "supported_capabilities",
]
