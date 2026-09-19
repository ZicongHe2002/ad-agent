from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from .enums import CapabilityName, CapabilityStatus


class PlatformCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    creator_monitoring: CapabilityStatus
    new_post_webhook: CapabilityStatus
    latest_posts: CapabilityStatus
    post_fetch: CapabilityStatus
    comment_read: CapabilityStatus
    top_level_comment: CapabilityStatus
    comment_reply: CapabilityStatus
    comment_delete: CapabilityStatus
    comment_created_at: CapabilityStatus
    chronological_rank: CapabilityStatus
    visible_rank: CapabilityStatus
    ai_disclosure: CapabilityStatus

    @classmethod
    def all_unknown(cls) -> PlatformCapabilities:
        return cls(**{field: CapabilityStatus.UNKNOWN for field in cls.model_fields})

    @classmethod
    def mock_supported(cls) -> PlatformCapabilities:
        return cls(**{field: CapabilityStatus.SUPPORTED for field in cls.model_fields})

    def status_for(self, capability: CapabilityName | str) -> CapabilityStatus:
        name = capability.value if isinstance(capability, CapabilityName) else capability
        field = name.lower()
        if field not in type(self).model_fields:
            raise KeyError(f"Unknown capability: {name}")
        value = getattr(self, field)
        return value if isinstance(value, CapabilityStatus) else CapabilityStatus(str(value))


@dataclass(frozen=True, slots=True)
class CapabilityCondition:
    authorization_required: bool = False
    required_scopes: tuple[str, ...] = ()
    account_types: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityCheck:
    capability: CapabilityName
    status: CapabilityStatus
    permitted: bool
    auto_publish_permitted: bool
    reason: str


def evaluate_capability(
    capability: CapabilityName,
    status: CapabilityStatus,
    *,
    conditions_satisfied: bool = False,
) -> CapabilityCheck:
    if status is CapabilityStatus.SUPPORTED:
        return CapabilityCheck(capability, status, True, True, "SUPPORTED")
    if status in {CapabilityStatus.CONDITIONAL, CapabilityStatus.AUTH_REQUIRED}:
        return CapabilityCheck(
            capability,
            status,
            conditions_satisfied,
            conditions_satisfied,
            "CONDITIONS_SATISFIED" if conditions_satisfied else "AUTH_OR_SCOPE_MISSING",
        )
    if status is CapabilityStatus.MANUAL:
        return CapabilityCheck(capability, status, True, False, "MANUAL_ONLY")
    if status is CapabilityStatus.RATE_LIMITED:
        return CapabilityCheck(capability, status, False, False, "RATE_LIMITED")
    return CapabilityCheck(capability, status, False, False, status.value)
