"""Platform-layer exceptions and stable error mapping.

The adapter layer deliberately exposes a small, typed error surface.  Callers can
decide whether to retry, send work to review, or use the manual workflow without
having to inspect vendor-specific messages.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class PlatformError(RuntimeError):
    """Base class for all errors crossing the platform adapter boundary."""

    code = "platform_error"
    retryable = False
    http_status = 502

    def __init__(
        self,
        message: str = "Platform operation failed",
        *,
        platform: str | None = None,
        capability: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.platform = platform
        self.capability = capability
        self.details = dict(details or {})


class UnsupportedCapabilityError(PlatformError):
    code = "unsupported_capability"
    http_status = 422


class UnknownCapabilityError(PlatformError):
    code = "unknown_capability"
    http_status = 422


class ConditionalCapabilityError(PlatformError):
    code = "capability_conditions_not_met"
    http_status = 403


class ManualWorkflowRequiredError(PlatformError):
    code = "manual_workflow_required"
    http_status = 409


class CapabilityDisabledError(PlatformError):
    code = "capability_disabled"
    http_status = 403


class AuthenticationRequiredError(PlatformError):
    code = "authentication_required"
    http_status = 401


class AuthorizationExpiredError(AuthenticationRequiredError):
    code = "authorization_expired"


class AuthorizationScopeError(AuthenticationRequiredError):
    code = "authorization_scope_missing"
    http_status = 403


class RateLimitedError(PlatformError):
    code = "rate_limited"
    retryable = True
    http_status = 429

    def __init__(
        self,
        message: str = "Platform rate limit reached",
        *,
        retry_after: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class PlatformTemporaryError(PlatformError):
    code = "platform_temporary_error"
    retryable = True
    http_status = 503


class PlatformTimeoutError(PlatformTemporaryError):
    code = "platform_timeout"
    http_status = 504


class PlatformPermanentError(PlatformError):
    code = "platform_permanent_error"
    http_status = 422


class PublishUncertainError(PlatformTemporaryError):
    """The platform may have accepted a publish before the response was lost."""

    code = "publish_uncertain"
    http_status = 504

    def __init__(
        self,
        message: str = "Publish outcome is uncertain",
        *,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.idempotency_key = idempotency_key


class PolicyBlockedError(PlatformError):
    code = "policy_blocked"
    http_status = 403


class IdempotencyConflictError(PlatformPermanentError):
    code = "idempotency_conflict"
    http_status = 409


class PlatformIntegrationNotConfiguredError(PlatformError):
    code = "official_integration_not_configured"
    http_status = 503


class PlatformNotRegisteredError(PlatformError):
    code = "platform_not_registered"
    http_status = 404


@dataclass(frozen=True)
class PlatformErrorInfo:
    code: str
    message: str
    retryable: bool
    http_status: int
    platform: str | None
    capability: str | None
    details: Mapping[str, Any]


def map_platform_exception(exc: BaseException) -> PlatformErrorInfo:
    """Convert any adapter exception to a log/API-safe description.

    Unknown exceptions are intentionally mapped to a retryable generic failure;
    their repr is not exposed because SDK exceptions can contain credentials.
    """

    if isinstance(exc, PlatformError):
        details = dict(exc.details)
        if isinstance(exc, RateLimitedError) and exc.retry_after is not None:
            details["retry_after"] = exc.retry_after
        if isinstance(exc, PublishUncertainError) and exc.idempotency_key:
            details["idempotency_key"] = exc.idempotency_key
        return PlatformErrorInfo(
            code=exc.code,
            message=str(exc),
            retryable=exc.retryable,
            http_status=exc.http_status,
            platform=exc.platform,
            capability=exc.capability,
            details=details,
        )
    return PlatformErrorInfo(
        code=PlatformTemporaryError.code,
        message="Unexpected platform integration failure",
        retryable=True,
        http_status=PlatformTemporaryError.http_status,
        platform=None,
        capability=None,
        details={},
    )


__all__ = [
    "AuthenticationRequiredError",
    "AuthorizationExpiredError",
    "AuthorizationScopeError",
    "CapabilityDisabledError",
    "ConditionalCapabilityError",
    "IdempotencyConflictError",
    "ManualWorkflowRequiredError",
    "PlatformError",
    "PlatformErrorInfo",
    "PlatformIntegrationNotConfiguredError",
    "PlatformNotRegisteredError",
    "PlatformPermanentError",
    "PlatformTemporaryError",
    "PlatformTimeoutError",
    "PolicyBlockedError",
    "PublishUncertainError",
    "RateLimitedError",
    "UnknownCapabilityError",
    "UnsupportedCapabilityError",
    "map_platform_exception",
]
