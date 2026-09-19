from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskPolicyResult:
    decision: str
    score: float
    matched_rules: tuple[str, ...]


BLOCKING_RELATIONSHIPS = {"COMPETITOR", "BLOCKED_CREATOR"}


def evaluate_hard_risk(context: Mapping[str, object]) -> RiskPolicyResult:
    matched: list[str] = []
    relationship = str(context.get("creator_relationship", ""))
    if relationship in BLOCKING_RELATIONSHIPS:
        matched.append("CREATOR_BLOCKED")
    gates = {
        "fake_experience": "FAKE_EXPERIENCE",
        "fake_identity": "FAKE_IDENTITY",
        "unapproved_claim": "UNAPPROVED_CLAIM",
        "external_contact": "EXTERNAL_CONTACT",
        "prohibited_phrase": "PROHIBITED_PHRASE",
        "daily_limit_exceeded": "DAILY_LIMIT",
        "creator_limit_exceeded": "CREATOR_DAILY_LIMIT",
        "duplicate_intent": "DUPLICATE_INTENT",
        "kill_switch": "KILL_SWITCH",
        "disclosure_unresolved": "DISCLOSURE_UNRESOLVED",
        "policy_expired": "POLICY_EXPIRED",
    }
    for source, rule in gates.items():
        if bool(context.get(source)):
            matched.append(rule)
    if matched:
        return RiskPolicyResult("BLOCK", 1.0, tuple(matched))
    if not bool(context.get("critical_dependencies_available", True)):
        return RiskPolicyResult("BLOCK", 1.0, ("FAIL_CLOSED",))
    return RiskPolicyResult("ALLOW", 0.0, ())


def combine_risk(rule: RiskPolicyResult, semantic_score: float | None) -> RiskPolicyResult:
    if rule.decision == "BLOCK":
        return rule
    if semantic_score is None:
        return rule
    score = max(0.0, min(1.0, semantic_score))
    if score < 0.30:
        return RiskPolicyResult("ALLOW", score, ())
    if score <= 0.65:
        return RiskPolicyResult("REVIEW", score, ("SEMANTIC_UNCERTAINTY",))
    return RiskPolicyResult("BLOCK", score, ("SEMANTIC_RISK",))
