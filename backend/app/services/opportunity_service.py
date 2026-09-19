from __future__ import annotations

from collections.abc import Mapping

RELATIONSHIP_MULTIPLIERS: dict[str, float] = {
    "OWN_ACCOUNT": 1.10,
    "PARTNER_CREATOR": 1.05,
    "OFFICIAL_CAMPAIGN_CREATOR": 1.05,
    "GENERAL_CREATOR": 0.90,
    "BRAND_ACCOUNT": 0.70,
    "COMPETITOR": 0.00,
    "BLOCKED_CREATOR": 0.00,
}


def compute_opportunity_score(values: Mapping[str, float], relationship: str) -> float:
    """Compute the canonical score; model-provided totals are never trusted.

    The source specification's weights yield a raw range of -10..90.  We apply
    the relationship multiplier and clamp to the documented 0..100 domain.
    """

    raw = (
        0.18 * values.get("creator_value", 0)
        + 0.22 * values.get("relevance", 0)
        + 0.15 * values.get("audience_match", 0)
        + 0.12 * values.get("traffic_potential", 0)
        + 0.08 * values.get("post_velocity", 0)
        + 0.15 * values.get("brand_fit", 0)
        - 0.05 * values.get("commercial_risk", 0)
        - 0.05 * values.get("platform_risk", 0)
    )
    multiplier = RELATIONSHIP_MULTIPLIERS.get(relationship, 0.0)
    return round(max(0.0, min(100.0, raw * multiplier)), 3)


def opportunity_band(score: float) -> str:
    if score >= 80:
        return "HIGH_PRIORITY_CANDIDATE"
    if score >= 65:
        return "REVIEW_CANDIDATE"
    if score >= 45:
        return "SLOW_PATH_OR_SKIP"
    return "SKIP"
