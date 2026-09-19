from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PublishRoute:
    mode: str
    reason: str | None = None
    retry_after_seconds: int | None = None


def build_idempotency_key(
    *,
    tenant_id: str,
    platform: str,
    brand_account_id: str,
    external_post_id: str,
    campaign_id: str,
    intent_key: str = "TOP_LEVEL_PRIMARY",
) -> str:
    canonical = "\x1f".join(
        (tenant_id, platform, brand_account_id, external_post_id, campaign_id, intent_key)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def route_publish(
    status: str,
    *,
    authorization_satisfies_conditions: bool = False,
    partner_capability: bool = False,
    retry_after_seconds: int | None = None,
    kill_switch: bool = False,
) -> PublishRoute:
    """Exhaustive routing for every CapabilityStatus.

    Unsupported automation is never attempted.  UNKNOWN and MANUAL are sent to
    a human workflow, while explicitly UNSUPPORTED remains distinguishable.
    """

    if kill_switch:
        return PublishRoute("BLOCKED", "KILL_SWITCH")
    if status == "SUPPORTED":
        return PublishRoute("OFFICIAL_PARTNER" if partner_capability else "OFFICIAL_API")
    if status == "CONDITIONAL":
        if authorization_satisfies_conditions:
            return PublishRoute("OFFICIAL_PARTNER" if partner_capability else "OFFICIAL_API")
        return PublishRoute("MANUAL", "CONDITIONS_NOT_SATISFIED")
    if status == "AUTH_REQUIRED":
        return PublishRoute("MANUAL", "AUTHORIZATION_REQUIRED")
    if status in {"UNKNOWN", "MANUAL"}:
        return PublishRoute("MANUAL", "TOP_LEVEL_COMMENT_NOT_VERIFIED")
    if status == "UNSUPPORTED":
        return PublishRoute("UNSUPPORTED", "PLATFORM_DOES_NOT_SUPPORT_OPERATION")
    if status == "RATE_LIMITED":
        return PublishRoute("DEFERRED", "RATE_LIMITED", retry_after_seconds)
    if status == "DISABLED":
        return PublishRoute("BLOCKED", "PLATFORM_DISABLED")
    return PublishRoute("BLOCKED", "INVALID_CAPABILITY_STATUS")


REQUIRED_AUTO_PUBLISH_GATES = (
    "state_ready",
    "risk_allowed",
    "quality_allowed",
    "identity_active",
    "campaign_active",
    "account_auth_valid",
    "capability_current",
    "idempotency_lock_acquired",
    "rate_limit_token_acquired",
    "auto_publish_enabled",
    "disclosure_resolved",
)


def validate_publish_preconditions(gates: Mapping[str, Any]) -> list[str]:
    return [name for name in REQUIRED_AUTO_PUBLISH_GATES if not bool(gates.get(name))]
