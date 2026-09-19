from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from .enums import CapabilityStatus, CreatorRelationship

RELATIONSHIP_MULTIPLIERS: dict[CreatorRelationship, float] = {
    CreatorRelationship.OWN_ACCOUNT: 1.10,
    CreatorRelationship.PARTNER_CREATOR: 1.05,
    CreatorRelationship.OFFICIAL_CAMPAIGN_CREATOR: 1.05,
    CreatorRelationship.GENERAL_CREATOR: 0.90,
    CreatorRelationship.BRAND_ACCOUNT: 0.70,
    CreatorRelationship.COMPETITOR: 0.00,
    CreatorRelationship.BLOCKED_CREATOR: 0.00,
}


def opportunity_score(
    *,
    creator_value: float,
    relevance: float,
    audience_match: float,
    traffic_potential: float,
    post_velocity: float,
    brand_fit: float,
    commercial_risk: float,
    platform_risk: float,
    relationship: CreatorRelationship | None = None,
) -> float:
    values = (
        creator_value,
        relevance,
        audience_match,
        traffic_potential,
        post_velocity,
        brand_fit,
        commercial_risk,
        platform_risk,
    )
    if any(value < 0 or value > 100 for value in values):
        raise ValueError("opportunity score components must be between 0 and 100")
    score = (
        0.18 * creator_value
        + 0.22 * relevance
        + 0.15 * audience_match
        + 0.12 * traffic_potential
        + 0.08 * post_velocity
        + 0.15 * brand_fit
        - 0.05 * commercial_risk
        - 0.05 * platform_risk
    )
    if relationship is not None:
        score *= RELATIONSHIP_MULTIPLIERS[relationship]
    return round(max(0.0, min(100.0, score)), 4)


def deterministic_jitter(entity_id: object, current_hour: datetime | None = None) -> float:
    hour = (current_hour or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%d%H")
    digest = hashlib.sha256(f"{entity_id}:{hour}".encode()).digest()
    return 0.85 + (int.from_bytes(digest[:4], "big") % 3000) / 10000


@dataclass(frozen=True, slots=True)
class PollingContext:
    creator_platform_account_id: object
    normal_interval_sec: int = 600
    warm_interval_sec: int = 60
    hot_interval_sec: int = 10
    priority: int = 50
    in_expected_publish_window: bool = False
    in_high_probability_window: bool = False
    recent_activity_score: float = 0.0
    failure_count: int = 0
    platform_rate_limit_pressure: float = 0.0
    capability_status: CapabilityStatus = CapabilityStatus.UNKNOWN
    monitor_paused: bool = False
    auth_invalid: bool = False
    current_hour: datetime | None = None


def next_poll_interval(context: PollingContext) -> int:
    if context.monitor_paused:
        return 3600
    if context.capability_status not in {
        CapabilityStatus.SUPPORTED,
        CapabilityStatus.CONDITIONAL,
        CapabilityStatus.AUTH_REQUIRED,
    }:
        return 3600
    if context.auth_invalid:
        return 1800

    base = context.normal_interval_sec
    if context.in_expected_publish_window:
        base = context.warm_interval_sec
    if context.priority >= 90 and context.in_high_probability_window:
        base = context.hot_interval_sec
    if context.recent_activity_score >= 0.8:
        base = min(base, context.warm_interval_sec)
    if context.failure_count > 0:
        base = max(base, min(3600, 2**context.failure_count * 15))
    if context.platform_rate_limit_pressure >= 0.8:
        base = int(base * 2.5)
    interval = int(
        base * deterministic_jitter(context.creator_platform_account_id, context.current_hour)
    )
    return max(5, min(3600, interval))
