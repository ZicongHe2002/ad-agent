"""Database-backed Mock Platform shared by API, scheduler, and worker processes."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import AsyncSessionFactory
from app.domain.capabilities import PlatformCapabilities
from app.domain.enums import CapabilityStatus
from app.models import (
    MockCommentRecord,
    MockCreatorRecord,
    MockPlatformState,
    MockPostRecord,
)
from app.platforms.base import (
    CommentPage,
    PlatformComment,
    PostPage,
    PublishCommentRequest,
    PublishReceipt,
    ReconcileRequest,
    ReconcileResult,
    ReplyCommentRequest,
    utc_now,
)
from app.platforms.errors import IdempotencyConflictError, PlatformPermanentError

from .failure_injection import FailureInjector, MockFailureProfile
from .ranking import chronological_rank, visible_comments, visible_rank
from .service import MockComment, MockCreator, MockPlatformPolicy, MockPost, supported_capabilities


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class PersistentMockPlatformService:
    """Implements the Mock Platform contract on the application's primary database.

    The original in-memory service remains useful for isolated unit tests. Runtime
    code uses this class so API and worker containers observe exactly the same data.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionFactory,
    ) -> None:
        self._sessions = session_factory
        self.failures = FailureInjector()

    async def _state(self, session: AsyncSession) -> MockPlatformState | None:
        return await session.get(MockPlatformState, "default")

    async def get_capabilities(self) -> PlatformCapabilities:
        async with self._sessions() as session:
            state = await self._state(session)
            if state is None or not state.capabilities:
                return supported_capabilities()
            return PlatformCapabilities(**state.capabilities)

    async def get_policy(self) -> MockPlatformPolicy:
        async with self._sessions() as session:
            state = await self._state(session)
            return MockPlatformPolicy(**(state.policy if state else {}))

    async def _injector(self) -> FailureInjector:
        async with self._sessions() as session:
            state = await self._state(session)
            profile = MockFailureProfile(**(state.failure_profile if state else {}))
        # Reload persisted configuration without replaying the first PRNG sample
        # on every request. Only an actual profile change starts a new sequence.
        if profile != self.failures.profile:
            self.failures.configure(profile)
        return self.failures

    async def _upsert_state(self, **values: dict[str, object]) -> MockPlatformState:
        async with self._sessions() as session, session.begin():
            state = await self._state(session)
            if state is None:
                state = MockPlatformState(key="default")
                session.add(state)
            for key, value in values.items():
                setattr(state, key, value)
            await session.flush()
            return state

    async def configure_failure_profile(
        self, profile: MockFailureProfile | Mapping[str, Any]
    ) -> MockFailureProfile:
        parsed = (
            profile if isinstance(profile, MockFailureProfile) else MockFailureProfile(**profile)
        )
        await self._upsert_state(failure_profile=parsed.model_dump(mode="json"))
        self.failures.configure(parsed)
        return parsed

    async def configure_capabilities(
        self, **statuses: CapabilityStatus | str
    ) -> PlatformCapabilities:
        current = (await self.get_capabilities()).model_dump(mode="json")
        unknown = set(statuses) - set(current)
        if unknown:
            raise ValueError(f"Unknown capability fields: {', '.join(sorted(unknown))}")
        current.update(
            {
                key: value.value if isinstance(value, CapabilityStatus) else str(value)
                for key, value in statuses.items()
            }
        )
        capabilities = PlatformCapabilities(**current)
        await self._upsert_state(capabilities=capabilities.model_dump(mode="json"))
        return capabilities

    async def configure_policy(
        self, policy: MockPlatformPolicy | Mapping[str, Any]
    ) -> MockPlatformPolicy:
        parsed = policy if isinstance(policy, MockPlatformPolicy) else MockPlatformPolicy(**policy)
        await self._upsert_state(policy=parsed.model_dump(mode="json"))
        return parsed

    async def reset(self) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(delete(MockCommentRecord))
            await session.execute(delete(MockPostRecord))
            await session.execute(delete(MockCreatorRecord))
            await session.execute(delete(MockPlatformState))
        self.failures.reset()

    @staticmethod
    def _creator(record: MockCreatorRecord) -> MockCreator:
        return MockCreator(
            external_creator_id=record.external_creator_id,
            name=record.name,
            created_at=_as_aware(record.created_at),
            metadata=record.platform_metadata,
        )

    @staticmethod
    def _post(record: MockPostRecord) -> MockPost:
        return MockPost(
            external_post_id=record.external_post_id,
            external_creator_id=record.external_creator_id,
            published_at=_as_aware(record.published_at),
            created_at=_as_aware(record.created_at),
            title=record.title,
            caption=record.caption,
            hashtags=record.hashtags,
            mentions=record.mentions,
            media_urls=record.media_urls,
            raw_payload=record.raw_payload,
        )

    @staticmethod
    def _comment(record: MockCommentRecord) -> MockComment:
        return MockComment(
            external_comment_id=record.external_comment_id,
            external_post_id=record.external_post_id,
            text=record.body,
            created_at=_as_aware(record.platform_created_at),
            author_external_id=record.author_external_id,
            parent_comment_id=record.parent_comment_id,
            like_count=record.like_count,
            author_pinned=record.author_pinned,
            visible_at=_as_aware(record.visible_at) if record.visible_at else None,
            raw_payload=record.raw_payload,
            idempotency_key=record.idempotency_key,
            account_id=record.account_id,
        )

    async def create_creator(
        self,
        name: str,
        *,
        external_creator_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MockCreator:
        creator_id = external_creator_id or f"mock-creator-{uuid4()}"
        async with self._sessions() as session, session.begin():
            if await session.get(MockCreatorRecord, creator_id):
                raise PlatformPermanentError("Mock creator already exists", platform="MOCK")
            record = MockCreatorRecord(
                external_creator_id=creator_id,
                name=name,
                platform_metadata=dict(metadata or {}),
            )
            session.add(record)
            await session.flush()
            return self._creator(record)

    async def list_creators(self) -> list[MockCreator]:
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    select(MockCreatorRecord).order_by(
                        MockCreatorRecord.created_at, MockCreatorRecord.external_creator_id
                    )
                )
            ).all()
            return [self._creator(item) for item in records]

    async def get_creator(self, external_creator_id: str) -> MockCreator:
        async with self._sessions() as session:
            record = await session.get(MockCreatorRecord, external_creator_id)
            if record is None:
                raise PlatformPermanentError("Mock creator not found", platform="MOCK")
            return self._creator(record)

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
        async with self._sessions() as session, session.begin():
            if await session.get(MockCreatorRecord, external_creator_id) is None:
                raise PlatformPermanentError("Mock creator not found", platform="MOCK")
            if await session.get(MockPostRecord, post_id):
                raise PlatformPermanentError("Mock post already exists", platform="MOCK")
            record = MockPostRecord(
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
            session.add(record)
            await session.flush()
            return self._post(record)

    async def get_latest_posts(
        self,
        external_creator_id: str,
        cursor: str | None = None,
        *,
        inject_failure: bool = True,
    ) -> PostPage:
        if inject_failure:
            await (await self._injector()).before_request("get_latest_posts")
        policy = await self.get_policy()
        offset = self._offset(cursor)
        async with self._sessions() as session:
            if await session.get(MockCreatorRecord, external_creator_id) is None:
                raise PlatformPermanentError("Mock creator not found", platform="MOCK")
            records = (
                await session.scalars(
                    select(MockPostRecord)
                    .where(MockPostRecord.external_creator_id == external_creator_id)
                    .order_by(
                        MockPostRecord.published_at.desc(), MockPostRecord.external_post_id.desc()
                    )
                    .offset(offset)
                    .limit(policy.page_size + 1)
                )
            ).all()
        has_more = len(records) > policy.page_size
        page = records[: policy.page_size]
        return PostPage(
            items=[self._post(item) for item in page],
            next_cursor=str(offset + len(page)) if has_more else None,
        )

    async def get_post(self, external_post_id: str, *, inject_failure: bool = True) -> MockPost:
        if inject_failure:
            await (await self._injector()).before_request("get_post")
        async with self._sessions() as session:
            record = await session.get(MockPostRecord, external_post_id)
            if record is None:
                raise PlatformPermanentError("Mock post not found", platform="MOCK")
            return self._post(record)

    @staticmethod
    def _offset(cursor: str | None) -> int:
        if not cursor:
            return 0
        try:
            value = int(cursor)
        except (TypeError, ValueError) as exc:
            raise PlatformPermanentError("Invalid pagination cursor", platform="MOCK") from exc
        if value < 0:
            raise PlatformPermanentError("Invalid pagination cursor", platform="MOCK")
        return value

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
        policy = await self.get_policy()
        visibility_delay = (await self._injector()).profile.visibility_delay_ms
        if not text.strip():
            raise PlatformPermanentError("Comment cannot be empty", platform="MOCK")
        if len(text) > policy.max_comment_length:
            raise PlatformPermanentError(
                "Comment exceeds mock platform length limit", platform="MOCK"
            )
        fingerprint = hashlib.sha256(
            f"{external_post_id}\x1f{account_id or ''}\x1f{text}\x1f{parent_comment_id or ''}".encode()
        ).hexdigest()
        async with self._sessions() as session, session.begin():
            if await session.get(MockPostRecord, external_post_id) is None:
                raise PlatformPermanentError("Mock post not found", platform="MOCK")
            if parent_comment_id:
                parent = await session.get(MockCommentRecord, parent_comment_id)
                if parent is None or parent.external_post_id != external_post_id:
                    raise PlatformPermanentError(
                        "Parent comment not found on target post", platform="MOCK"
                    )
            if idempotency_key:
                existing = await session.scalar(
                    select(MockCommentRecord).where(
                        MockCommentRecord.idempotency_key == idempotency_key
                    )
                )
                if existing:
                    if existing.request_fingerprint != fingerprint:
                        raise IdempotencyConflictError(
                            "Idempotency key was already used for different content",
                            platform="MOCK",
                            details={"idempotency_key": idempotency_key},
                        )
                    return self._comment(existing), False
            timestamp = created_at or utc_now()
            record = MockCommentRecord(
                external_comment_id=f"mock-comment-{uuid4()}",
                external_post_id=external_post_id,
                body=text,
                platform_created_at=timestamp,
                author_external_id=author_external_id,
                parent_comment_id=parent_comment_id,
                like_count=max(0, like_count),
                author_pinned=author_pinned,
                visible_at=timestamp + timedelta(milliseconds=visibility_delay),
                raw_payload=dict(raw_payload or {}),
                idempotency_key=idempotency_key,
                account_id=account_id,
                request_fingerprint=fingerprint,
            )
            session.add(record)
            await session.flush()
            return self._comment(record), True

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
        injector = await self._injector()
        await injector.before_request("publish_top_level_comment")
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
            # Reload so a persisted profile is honored in every process.
            (await self._injector()).after_publish(idempotency_key=request.idempotency_key)
        return receipt

    async def reply_comment(self, request: ReplyCommentRequest) -> PublishReceipt:
        injector = await self._injector()
        await injector.before_request("reply_comment")
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
            (await self._injector()).after_publish(idempotency_key=request.idempotency_key)
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
            body = (
                texts[index] if texts and index < len(texts) else f"Simulated comment {index + 1}"
            )
            comment, _ = await self._create_comment(
                external_post_id=external_post_id,
                text=body,
                author_external_id=f"simulated-user-{index + 1}",
                parent_comment_id=None,
                idempotency_key=None,
                account_id=None,
                created_at=base + timedelta(milliseconds=index * interval_ms),
                like_count=index,
            )
            result.append(comment)
        return result

    async def _all_comments(self, external_post_id: str) -> list[MockComment]:
        async with self._sessions() as session:
            if await session.get(MockPostRecord, external_post_id) is None:
                raise PlatformPermanentError("Mock post not found", platform="MOCK")
            records = (
                await session.scalars(
                    select(MockCommentRecord)
                    .where(MockCommentRecord.external_post_id == external_post_id)
                    .order_by(
                        MockCommentRecord.platform_created_at,
                        MockCommentRecord.external_comment_id,
                    )
                )
            ).all()
            return [self._comment(item) for item in records]

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
            await (await self._injector()).before_request("get_comments")
        items: list[PlatformComment] = list(await self._all_comments(external_post_id))
        now = utc_now()
        if visible_only:
            items = [
                item
                for item in items
                if item.visible_at is None or _as_aware(item.visible_at) <= now
            ]
        if top_level_only:
            items = [item for item in items if item.parent_comment_id is None]
        policy = await self.get_policy()
        if order.lower() == "visible":
            items = visible_comments(
                items,
                policy.visible_ranking,
                seed=f"{policy.ranking_seed}:{external_post_id}",
                viewer_id=viewer_id,
            )
        else:
            items.sort(key=lambda item: (_as_aware(item.created_at), item.external_comment_id))
        offset = self._offset(cursor)
        page = items[offset : offset + policy.page_size]
        following = offset + len(page)
        return CommentPage(
            items=page,
            next_cursor=str(following) if following < len(items) else None,
        )

    async def comment_ranks(
        self,
        external_post_id: str,
        external_comment_id: str,
        *,
        viewer_id: str = "default",
    ) -> tuple[int, int]:
        all_items = await self._all_comments(external_post_id)
        now = utc_now()
        items = [
            item
            for item in all_items
            if item.parent_comment_id is None
            and (item.visible_at is None or _as_aware(item.visible_at) <= now)
        ]
        policy = await self.get_policy()
        return (
            chronological_rank(items, external_comment_id),
            visible_rank(
                items,
                external_comment_id,
                policy.visible_ranking,
                seed=f"{policy.ranking_seed}:{external_post_id}",
                viewer_id=viewer_id,
            ),
        )

    async def reconcile_publish(self, request: ReconcileRequest) -> ReconcileResult:
        await (await self._injector()).before_request("reconcile_publish")
        async with self._sessions() as session:
            record = await session.scalar(
                select(MockCommentRecord).where(
                    MockCommentRecord.idempotency_key == request.idempotency_key
                )
            )
            if (
                record is None
                or record.external_post_id != request.external_post_id
                or record.account_id != request.account_id
            ):
                return ReconcileResult(found=False, status="NOT_FOUND")
            return ReconcileResult(
                found=True,
                status="PUBLISHED",
                receipt=self._receipt(self._comment(record)),
            )


__all__ = ["PersistentMockPlatformService"]
