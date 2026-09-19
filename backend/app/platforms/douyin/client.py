"""Safe port for an official Douyin SDK/client.

This module intentionally contains no guessed URLs and no HTTP implementation.
Production wiring must inject a client built from verified official documentation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Protocol, TypeVar

from ..base import (
    AuthorizationContext,
    CommentPage,
    PlatformPost,
    PostPage,
    PublishReceipt,
    ReconcileRequest,
    ReconcileResult,
    ReplyCommentRequest,
)
from ..errors import (
    AuthorizationExpiredError,
    AuthorizationScopeError,
    PlatformError,
    PlatformIntegrationNotConfiguredError,
    PlatformTemporaryError,
    PlatformTimeoutError,
    PublishUncertainError,
)

ResultT = TypeVar("ResultT")


class OfficialDouyinTransport(Protocol):
    """An audited transport holding credentials for exactly one authorization.

    Implementations must not select credentials from request metadata or retry a
    timed-out write. Reconciliation must use official evidence for the original
    account and intent; absence of such evidence is not proof of non-publication.
    """

    async def get_latest_posts(
        self, external_creator_id: str, cursor: str | None, trace_id: str
    ) -> PostPage: ...

    async def get_post(self, external_post_id: str, trace_id: str) -> PlatformPost: ...

    async def get_comments(
        self, external_post_id: str, cursor: str | None, trace_id: str
    ) -> CommentPage: ...

    async def reply_comment(self, request: ReplyCommentRequest) -> PublishReceipt: ...

    async def reconcile_publish(self, request: ReconcileRequest) -> ReconcileResult: ...


class DouyinClient:
    """Timeout-enforcing wrapper around an injected official transport."""

    def __init__(
        self,
        transport: OfficialDouyinTransport | None = None,
        *,
        authorization: AuthorizationContext | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._transport = transport
        self._authorization = authorization.model_copy(deep=True) if authorization else None
        self.timeout_seconds = timeout_seconds

    @property
    def authorization(self) -> AuthorizationContext | None:
        return self._authorization.model_copy(deep=True) if self._authorization else None

    @property
    def configured(self) -> bool:
        auth = self._authorization
        return bool(
            self._transport is not None
            and auth is not None
            and auth.present
            and auth.account_id
            and auth.external_creator_id
            and not auth.is_expired()
        )

    def require_authorization(
        self, expected: AuthorizationContext | None = None
    ) -> AuthorizationContext:
        auth = self._authorization
        if auth is None or not auth.present or not auth.account_id or not auth.external_creator_id:
            raise PlatformIntegrationNotConfiguredError(
                "Official Douyin credentials must be bound to one account and creator",
                platform="DOUYIN",
            )
        if auth.is_expired():
            raise AuthorizationExpiredError(platform="DOUYIN")
        if expected is not None and expected != auth:
            raise AuthorizationScopeError(
                "Adapter authorization does not match the official client's credential binding",
                platform="DOUYIN",
            )
        return auth.model_copy(deep=True)

    def _require_account(self, account_id: str) -> None:
        if self.require_authorization().account_id != account_id:
            raise AuthorizationScopeError(
                "Request account does not match the official client's credential binding",
                platform="DOUYIN",
            )

    def _require_transport(self) -> OfficialDouyinTransport:
        if self._transport is None:
            raise PlatformIntegrationNotConfiguredError(
                "An audited official Douyin transport has not been configured",
                platform="DOUYIN",
            )
        self.require_authorization()
        return self._transport

    async def _call(
        self,
        awaitable: Awaitable[ResultT],
        operation: str,
        *,
        publish_idempotency_key: str | None = None,
    ) -> ResultT:
        try:
            return await asyncio.wait_for(awaitable, timeout=self.timeout_seconds)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            if publish_idempotency_key is not None:
                raise PublishUncertainError(
                    "Official Douyin reply may have succeeded before the timeout",
                    platform="DOUYIN",
                    idempotency_key=publish_idempotency_key,
                    details={"operation": operation},
                ) from exc
            raise PlatformTimeoutError(
                "Official Douyin request timed out",
                platform="DOUYIN",
                details={"operation": operation},
            ) from exc
        except PlatformTimeoutError as exc:
            if publish_idempotency_key is not None:
                raise PublishUncertainError(
                    "Official Douyin reply may have succeeded before the timeout",
                    platform="DOUYIN",
                    idempotency_key=publish_idempotency_key,
                    details={"operation": operation},
                ) from exc
            raise
        except PlatformError:
            raise
        except Exception as exc:
            # Never leak SDK response bodies or authorization values.
            if publish_idempotency_key is not None:
                raise PublishUncertainError(
                    "Official Douyin reply outcome could not be confirmed",
                    platform="DOUYIN",
                    idempotency_key=publish_idempotency_key,
                    details={"operation": operation},
                ) from exc
            raise PlatformTemporaryError(
                "Official Douyin transport failed",
                platform="DOUYIN",
                details={"operation": operation},
            ) from exc

    async def get_latest_posts(
        self, external_creator_id: str, cursor: str | None, trace_id: str
    ) -> PostPage:
        transport = self._require_transport()
        if self.require_authorization().external_creator_id != external_creator_id:
            raise AuthorizationScopeError(
                "Requested creator is outside the credential binding", platform="DOUYIN"
            )
        return await self._call(
            transport.get_latest_posts(external_creator_id, cursor, trace_id), "get_latest_posts"
        )

    async def get_post(self, external_post_id: str, trace_id: str) -> PlatformPost:
        transport = self._require_transport()
        return await self._call(transport.get_post(external_post_id, trace_id), "get_post")

    async def get_comments(
        self, external_post_id: str, cursor: str | None, trace_id: str
    ) -> CommentPage:
        transport = self._require_transport()
        return await self._call(
            transport.get_comments(external_post_id, cursor, trace_id), "get_comments"
        )

    async def reply_comment(self, request: ReplyCommentRequest) -> PublishReceipt:
        transport = self._require_transport()
        self._require_account(request.account_id)
        receipt = await self._call(
            transport.reply_comment(request),
            "reply_comment",
            publish_idempotency_key=request.idempotency_key,
        )
        if (
            receipt.external_post_id != request.external_post_id
            or receipt.idempotency_key != request.idempotency_key
            or not receipt.accepted
        ):
            raise PublishUncertainError(
                "Official reply receipt does not confirm the requested intent",
                platform="DOUYIN",
                idempotency_key=request.idempotency_key,
            )
        return receipt

    async def reconcile_publish(self, request: ReconcileRequest) -> ReconcileResult:
        transport = self._require_transport()
        self._require_account(request.account_id)
        result = await self._call(transport.reconcile_publish(request), "reconcile_publish")
        if result.found and (
            result.receipt is None
            or result.receipt.external_post_id != request.external_post_id
            or result.receipt.idempotency_key != request.idempotency_key
            or not result.receipt.accepted
        ):
            raise PlatformTemporaryError(
                "Official reconciliation did not provide a matching confirmed receipt",
                platform="DOUYIN",
            )
        return result


__all__ = ["DouyinClient", "OfficialDouyinTransport"]
