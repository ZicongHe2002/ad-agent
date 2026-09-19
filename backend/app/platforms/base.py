"""Vendor-neutral platform contract and capability enforcement.

Every external operation must pass :func:`require_official_capability`.  In
particular, ``UNKNOWN`` and reply-only capability can never silently become a
top-level publish capability.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ..domain.capabilities import PlatformCapabilities
from ..domain.enums import CapabilityName, CapabilityStatus, Platform
from .errors import (
    AuthenticationRequiredError,
    AuthorizationExpiredError,
    AuthorizationScopeError,
    CapabilityDisabledError,
    ConditionalCapabilityError,
    ManualWorkflowRequiredError,
    PolicyBlockedError,
    RateLimitedError,
    UnknownCapabilityError,
    UnsupportedCapabilityError,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CapabilityRoute(str, Enum):
    OFFICIAL = "OFFICIAL"
    MANUAL = "MANUAL"
    RETRY_LATER = "RETRY_LATER"
    BLOCKED = "BLOCKED"


class CapabilityScope(BaseModel):
    """Verified limits of a capability, not inferred permissions."""

    account_types: list[str] = Field(default_factory=list)
    target_content_types: list[str] = Field(default_factory=list)
    authorization_required: bool = False
    required_authorization_scopes: list[str] = Field(default_factory=list)
    allowed_external_creator_ids: list[str] = Field(default_factory=list)


class CapabilityRecord(BaseModel):
    platform: Platform
    capability: CapabilityName
    status: CapabilityStatus
    verified_at: datetime | None = None
    expires_at: datetime | None = None
    source_title: str | None = None
    source_owner: str | None = None
    scope: CapabilityScope = Field(default_factory=CapabilityScope)
    limitations: list[str] = Field(default_factory=list)
    verified_by: str | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        current = now or utc_now()
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return expires <= current


class AuthorizationContext(BaseModel):
    authorization_id: str | None = None
    account_id: str | None = None
    granted_scopes: frozenset[str] = Field(default_factory=frozenset)
    account_type: str | None = None
    target_content_type: str | None = None
    external_creator_id: str | None = None
    expires_at: datetime | None = None

    @property
    def present(self) -> bool:
        return bool(self.authorization_id)

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        current = now or utc_now()
        expiry = self.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return expiry <= current


class CapabilityUseContext(BaseModel):
    authorization: AuthorizationContext | None = None
    conditions_satisfied: bool = False
    manual_workflow_available: bool = True
    now: datetime | None = None
    retry_after: float | None = None


class CapabilityCheckResult(BaseModel):
    capability: CapabilityName
    status: CapabilityStatus
    allowed: bool
    route: CapabilityRoute
    reason: str
    missing_scopes: list[str] = Field(default_factory=list)


def _coerce_capability_name(value: CapabilityName | str) -> CapabilityName:
    if isinstance(value, CapabilityName):
        return value
    return CapabilityName(str(value).upper())


def _capability_status(
    capabilities: PlatformCapabilities, capability: CapabilityName
) -> CapabilityStatus:
    value = getattr(capabilities, capability.value.lower())
    return value if isinstance(value, CapabilityStatus) else CapabilityStatus(str(value))


def _scope_failure(
    record: CapabilityRecord | None,
    context: CapabilityUseContext,
) -> tuple[str | None, list[str]]:
    if record is None:
        return None, []
    now = context.now or utc_now()
    if record.is_expired(now):
        return "Capability verification has expired", []
    scope = record.scope
    auth = context.authorization
    if scope.authorization_required and (auth is None or not auth.present):
        return "Authorization is required", list(scope.required_authorization_scopes)
    if auth is not None and auth.is_expired(now):
        return "Authorization has expired", []
    if scope.account_types and (auth is None or auth.account_type not in scope.account_types):
        return "Account type is outside the verified capability scope", []
    if scope.target_content_types and (
        auth is None or auth.target_content_type not in scope.target_content_types
    ):
        return "Target content type is outside the verified capability scope", []
    if scope.allowed_external_creator_ids and (
        auth is None or auth.external_creator_id not in scope.allowed_external_creator_ids
    ):
        return "Creator is outside the verified capability scope", []
    granted = auth.granted_scopes if auth is not None else frozenset()
    missing = sorted(set(scope.required_authorization_scopes) - set(granted))
    if missing:
        return "Required authorization scopes are missing", missing
    return None, []


def evaluate_capability(
    capabilities: PlatformCapabilities,
    capability: CapabilityName | str,
    *,
    context: CapabilityUseContext | None = None,
    record: CapabilityRecord | None = None,
) -> CapabilityCheckResult:
    """Evaluate all eight capability states without performing I/O."""

    name = _coerce_capability_name(capability)
    status = _capability_status(capabilities, name)
    use = context or CapabilityUseContext()

    if status == CapabilityStatus.UNKNOWN:
        return CapabilityCheckResult(
            capability=name,
            status=status,
            allowed=False,
            route=CapabilityRoute.BLOCKED,
            reason="Capability has not been verified",
        )
    if status == CapabilityStatus.UNSUPPORTED:
        return CapabilityCheckResult(
            capability=name,
            status=status,
            allowed=False,
            route=CapabilityRoute.BLOCKED,
            reason="Capability is not supported",
        )
    if status == CapabilityStatus.DISABLED:
        return CapabilityCheckResult(
            capability=name,
            status=status,
            allowed=False,
            route=CapabilityRoute.BLOCKED,
            reason="Capability is administratively disabled",
        )
    if status == CapabilityStatus.RATE_LIMITED:
        return CapabilityCheckResult(
            capability=name,
            status=status,
            allowed=False,
            route=CapabilityRoute.RETRY_LATER,
            reason="Capability is currently rate limited",
        )
    if status == CapabilityStatus.MANUAL:
        return CapabilityCheckResult(
            capability=name,
            status=status,
            allowed=False,
            route=CapabilityRoute.MANUAL,
            reason="Capability requires the manual workflow",
        )

    scope_reason, missing = _scope_failure(record, use)
    if scope_reason:
        return CapabilityCheckResult(
            capability=name,
            status=status,
            allowed=False,
            route=CapabilityRoute.BLOCKED,
            reason=scope_reason,
            missing_scopes=missing,
        )

    auth = use.authorization
    if status == CapabilityStatus.AUTH_REQUIRED:
        if auth is None or not auth.present:
            return CapabilityCheckResult(
                capability=name,
                status=status,
                allowed=False,
                route=CapabilityRoute.BLOCKED,
                reason="Capability requires authorization",
            )
        if auth.is_expired(use.now):
            return CapabilityCheckResult(
                capability=name,
                status=status,
                allowed=False,
                route=CapabilityRoute.BLOCKED,
                reason="Authorization has expired",
            )

    if status == CapabilityStatus.CONDITIONAL and not use.conditions_satisfied:
        route = CapabilityRoute.MANUAL if use.manual_workflow_available else CapabilityRoute.BLOCKED
        return CapabilityCheckResult(
            capability=name,
            status=status,
            allowed=False,
            route=route,
            reason="Verified capability conditions are not satisfied",
        )

    # SUPPORTED, an authorized AUTH_REQUIRED, or a verified CONDITIONAL state.
    return CapabilityCheckResult(
        capability=name,
        status=status,
        allowed=True,
        route=CapabilityRoute.OFFICIAL,
        reason="Capability and scope checks passed",
    )


def require_official_capability(
    capabilities: PlatformCapabilities,
    capability: CapabilityName | str,
    *,
    platform: Platform | str,
    context: CapabilityUseContext | None = None,
    record: CapabilityRecord | None = None,
) -> CapabilityCheckResult:
    """Require an official-call route or raise a typed, policy-safe error."""

    result = evaluate_capability(capabilities, capability, context=context, record=record)
    if result.allowed:
        return result
    platform_value = platform.value if isinstance(platform, Platform) else str(platform)
    if result.status == CapabilityStatus.UNKNOWN:
        raise UnknownCapabilityError(
            result.reason,
            platform=platform_value,
            capability=result.capability.value,
        )
    if result.status == CapabilityStatus.UNSUPPORTED:
        raise UnsupportedCapabilityError(
            result.reason,
            platform=platform_value,
            capability=result.capability.value,
        )
    if result.status == CapabilityStatus.DISABLED:
        raise CapabilityDisabledError(
            result.reason,
            platform=platform_value,
            capability=result.capability.value,
        )
    if result.status == CapabilityStatus.RATE_LIMITED:
        retry_after = context.retry_after if context else None
        raise RateLimitedError(
            result.reason,
            retry_after=retry_after,
            platform=platform_value,
            capability=result.capability.value,
        )
    if result.status == CapabilityStatus.MANUAL or result.route == CapabilityRoute.MANUAL:
        raise ManualWorkflowRequiredError(
            result.reason,
            platform=platform_value,
            capability=result.capability.value,
        )
    if "expired" in result.reason.lower():
        if "authorization" in result.reason.lower():
            raise AuthorizationExpiredError(
                result.reason,
                platform=platform_value,
                capability=result.capability.value,
            )
        raise PolicyBlockedError(
            result.reason,
            platform=platform_value,
            capability=result.capability.value,
        )
    if result.missing_scopes:
        raise AuthorizationScopeError(
            result.reason,
            platform=platform_value,
            capability=result.capability.value,
            details={"missing_scopes": result.missing_scopes},
        )
    if result.status == CapabilityStatus.AUTH_REQUIRED or "authorization" in result.reason.lower():
        raise AuthenticationRequiredError(
            result.reason,
            platform=platform_value,
            capability=result.capability.value,
        )
    if result.status == CapabilityStatus.CONDITIONAL:
        raise ConditionalCapabilityError(
            result.reason,
            platform=platform_value,
            capability=result.capability.value,
        )
    raise PolicyBlockedError(
        result.reason,
        platform=platform_value,
        capability=result.capability.value,
    )


class CreatorPlatformRef(BaseModel):
    external_creator_id: str
    authorization_id: str | None = None
    account_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlatformPost(BaseModel):
    external_post_id: str
    source_url: str | None = None
    external_creator_id: str
    published_at: datetime
    title: str | None = None
    caption: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    media_urls: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class PostPage(BaseModel):
    items: list[PlatformPost] = Field(default_factory=list)
    next_cursor: str | None = None

    @property
    def posts(self) -> list[PlatformPost]:
        return self.items


class PlatformComment(BaseModel):
    external_comment_id: str
    external_post_id: str
    text: str
    created_at: datetime
    author_external_id: str | None = None
    parent_comment_id: str | None = None
    like_count: int = 0
    author_pinned: bool = False
    visible_at: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class CommentPage(BaseModel):
    items: list[PlatformComment] = Field(default_factory=list)
    next_cursor: str | None = None

    @property
    def comments(self) -> list[PlatformComment]:
        return self.items


class PublishCommentRequest(BaseModel):
    external_post_id: str
    text: str = Field(min_length=1)
    account_id: str
    idempotency_key: str = Field(min_length=1)
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    disclosure: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplyCommentRequest(PublishCommentRequest):
    parent_comment_id: str


class PublishReceipt(BaseModel):
    external_comment_id: str
    external_post_id: str
    created_at: datetime
    idempotency_key: str
    accepted: bool = True
    visible_at: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ReconcileRequest(BaseModel):
    external_post_id: str
    account_id: str
    idempotency_key: str
    trace_id: str = Field(default_factory=lambda: str(uuid4()))


class ReconcileResult(BaseModel):
    found: bool
    status: str
    receipt: PublishReceipt | None = None
    checked_at: datetime = Field(default_factory=utc_now)


class PlatformIntegrationStatus(BaseModel):
    """Deployment wiring only; capability evidence and authorization still apply."""

    platform: Platform
    configured: bool = False
    top_level_publish_configured: bool = False
    reason: str = "OFFICIAL_INTEGRATION_NOT_CONFIGURED"
    source_urls: list[str] = Field(default_factory=list)


class PlatformAdapter(ABC):
    platform: Platform

    async def get_integration_status(self) -> PlatformIntegrationStatus:
        return PlatformIntegrationStatus(platform=self.platform)

    @abstractmethod
    async def get_capabilities(self) -> PlatformCapabilities:
        raise NotImplementedError

    @abstractmethod
    async def get_latest_posts(self, creator: Any, cursor: str | None = None) -> PostPage:
        raise NotImplementedError

    @abstractmethod
    async def get_post(self, external_post_id: str) -> PlatformPost:
        raise NotImplementedError

    @abstractmethod
    async def get_comments(self, external_post_id: str, cursor: str | None = None) -> CommentPage:
        raise NotImplementedError

    @abstractmethod
    async def publish_top_level_comment(self, request: PublishCommentRequest) -> PublishReceipt:
        raise NotImplementedError

    @abstractmethod
    async def reply_comment(self, request: ReplyCommentRequest) -> PublishReceipt:
        raise NotImplementedError

    @abstractmethod
    async def reconcile_publish(self, request: ReconcileRequest) -> ReconcileResult:
        raise NotImplementedError


__all__ = [
    "AuthorizationContext",
    "CapabilityCheckResult",
    "CapabilityName",
    "CapabilityRecord",
    "CapabilityRoute",
    "CapabilityScope",
    "CapabilityUseContext",
    "CommentPage",
    "CreatorPlatformRef",
    "PlatformAdapter",
    "PlatformComment",
    "PlatformIntegrationStatus",
    "PlatformPost",
    "PostPage",
    "PublishCommentRequest",
    "PublishReceipt",
    "ReconcileRequest",
    "ReconcileResult",
    "ReplyCommentRequest",
    "evaluate_capability",
    "require_official_capability",
]
