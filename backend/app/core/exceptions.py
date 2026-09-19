from __future__ import annotations

from typing import Any


class DomainError(Exception):
    code = "DOMAIN_ERROR"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    code = "NOT_FOUND"


class ConflictError(DomainError):
    code = "CONFLICT"


class ValidationError(DomainError):
    code = "VALIDATION_ERROR"


class AuthenticationError(DomainError):
    code = "AUTHENTICATION_REQUIRED"


class AuthorizationError(DomainError):
    code = "FORBIDDEN"


class InvalidStateTransition(ConflictError):
    code = "INVALID_STATE_TRANSITION"

    def __init__(self, source: object, target: object) -> None:
        source_value = getattr(source, "value", str(source))
        target_value = getattr(target, "value", str(target))
        super().__init__(
            f"Cannot transition comment job from {source_value} to {target_value}",
            details={"source": source_value, "target": target_value},
        )
