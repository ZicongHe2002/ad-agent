from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class QualityPolicyResult:
    decision: str
    score: float
    reasons: tuple[str, ...]


HARD_FAILURE_FIELDS = (
    "fake_experience_detected",
    "fake_identity_detected",
    "unsupported_claim_detected",
)

QUALITY_SCORE_FIELDS = (
    "anchor_coverage",
    "specificity",
    "fluency",
    "voice_match",
    "novelty",
    "truthfulness",
)


def _numeric_value(value: object) -> float:
    """Return a finite policy input for JSON-compatible numeric values."""

    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def quality_score(parts: Mapping[str, float]) -> float:
    value = (
        0.25 * parts.get("anchor_coverage", 0)
        + 0.20 * parts.get("specificity", 0)
        + 0.15 * parts.get("fluency", 0)
        + 0.15 * parts.get("voice_match", 0)
        + 0.15 * parts.get("novelty", 0)
        + 0.10 * parts.get("truthfulness", 0)
    )
    return round(max(0.0, min(1.0, value)), 4)


def decide_quality(values: Mapping[str, object]) -> QualityPolicyResult:
    reasons: list[str] = []
    for field in HARD_FAILURE_FIELDS:
        if bool(values.get(field)):
            reasons.append(field.upper())
    if reasons:
        parts = {field: _numeric_value(values.get(field, 0)) for field in QUALITY_SCORE_FIELDS}
        return QualityPolicyResult("BLOCK", quality_score(parts), tuple(reasons))

    duplicate = _numeric_value(values.get("duplicate_similarity_max", 0))
    parts = {field: _numeric_value(values.get(field, 0)) for field in QUALITY_SCORE_FIELDS}
    score = quality_score(parts)
    if duplicate >= 0.90:
        return QualityPolicyResult("BLOCK", score, ("DUPLICATE",))
    if duplicate >= 0.82:
        return QualityPolicyResult("REVIEW", score, ("NEAR_DUPLICATE",))
    if score >= 0.80:
        return QualityPolicyResult("ALLOW", score, ())
    if score >= 0.65:
        return QualityPolicyResult("REVIEW", score, ("QUALITY_REVIEW",))
    return QualityPolicyResult("REGENERATE", score, ("QUALITY_TOO_LOW",))
