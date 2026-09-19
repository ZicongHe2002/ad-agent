"""Two-layer risk evaluation with immutable hard gates and fail-closed semantics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import RiskDecision
from app.prompts import PromptLoader

from .provider import LLMMessage, LLMProvider, LLMProviderError, MessageRole
from .structured_output import StructuredOutputError, generate_structured


class RiskAssessment(BaseModel):
    decision: RiskDecision
    risk_score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    matched_policy_categories: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)


class RuleRiskResult(BaseModel):
    decision: RiskDecision
    risk_score: float = Field(ge=0, le=1)
    matched_rules: list[str] = Field(default_factory=list)
    uncertain_categories: list[str] = Field(default_factory=list)


def _data(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    return {key: item for key, item in vars(value).items() if not key.startswith("_")}


class RuleRiskEngine:
    """Deterministic checks that an LLM or reviewer may never override."""

    def evaluate(self, context: Mapping[str, Any] | Any) -> RuleRiskResult:
        data = _data(context)
        matched: list[str] = []
        relationship = str(
            getattr(
                data.get("creator_relationship", ""), "value", data.get("creator_relationship", "")
            )
        )
        if relationship in {"COMPETITOR", "BLOCKED_CREATOR"}:
            matched.append("CREATOR_RELATIONSHIP_BLOCK")
        gates = {
            "fake_experience": "FAKE_EXPERIENCE",
            "fake_identity": "FAKE_IDENTITY",
            "unapproved_claim": "UNAPPROVED_CLAIM",
            "external_contact": "OFF_PLATFORM_DIVERSION",
            "prohibited_phrase": "PROHIBITED_PHRASE",
            "account_daily_limit_exceeded": "ACCOUNT_DAILY_LIMIT",
            "creator_daily_limit_exceeded": "CREATOR_DAILY_LIMIT",
            "campaign_daily_limit_exceeded": "CAMPAIGN_DAILY_LIMIT",
            "duplicate_idempotency_key": "DUPLICATE_INTENT",
            "platform_kill_switch": "PLATFORM_KILL_SWITCH",
            "account_kill_switch": "ACCOUNT_KILL_SWITCH",
            "campaign_kill_switch": "CAMPAIGN_KILL_SWITCH",
            "global_kill_switch": "GLOBAL_KILL_SWITCH",
            "policy_expired": "POLICY_EXPIRED",
            "identity_missing": "IDENTITY_MISSING",
            "claims_unavailable": "CLAIMS_UNAVAILABLE",
            "capability_registry_unavailable": "CAPABILITY_REGISTRY_UNAVAILABLE",
        }
        matched.extend(rule for flag, rule in gates.items() if bool(data.get(flag)))
        # Lack of automated platform capability is routed to MANUAL and is not a
        # content-risk block.  An attempted bypass, however, is a hard block.
        if bool(data.get("capability_bypass_attempted")):
            matched.append("CAPABILITY_BYPASS")
        if matched:
            return RuleRiskResult(
                decision=RiskDecision.BLOCK,
                risk_score=1.0,
                matched_rules=list(dict.fromkeys(matched)),
            )
        uncertain = [
            str(item) for item in data.get("uncertain_categories", ()) if str(item).strip()
        ]
        if bool(data.get("disclosure_unresolved")):
            uncertain.append("DISCLOSURE_UNRESOLVED")
        if bool(data.get("capability_manual_required")):
            uncertain.append("CAPABILITY_REQUIRES_MANUAL_ROUTE")
        if relationship == "GENERAL_CREATOR" and bool(data.get("brand_mentioned")):
            uncertain.append("GENERAL_CREATOR_BRAND_MENTION")
        uncertain = list(dict.fromkeys(uncertain))
        return RuleRiskResult(
            decision=RiskDecision.REVIEW if uncertain else RiskDecision.ALLOW,
            risk_score=0.4 if uncertain else 0.0,
            uncertain_categories=uncertain,
        )


class LLMRiskAgent:
    def __init__(self, provider: LLMProvider, *, prompt_loader: PromptLoader | None = None) -> None:
        self.provider = provider
        self.prompt_loader = prompt_loader or PromptLoader()

    async def evaluate(self, context: Mapping[str, Any]) -> RiskAssessment:
        artifact = self.prompt_loader.load("risk_check")
        result = await generate_structured(
            self.provider,
            [
                LLMMessage(role=MessageRole.SYSTEM, content=artifact.content),
                LLMMessage(
                    role=MessageRole.USER,
                    content=json.dumps(dict(context), ensure_ascii=False, default=str),
                ),
            ],
            response_model=RiskAssessment,
            timeout_seconds=getattr(self.provider, "timeout_seconds", 1.5),
            metadata={
                "prompt_name": artifact.name,
                "prompt_version": artifact.version,
                "prompt_hash": artifact.sha256,
            },
        )
        return result.value


class RiskAgent:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        *,
        rule_engine: RuleRiskEngine | None = None,
    ) -> None:
        self.rule_engine = rule_engine or RuleRiskEngine()
        self.llm = LLMRiskAgent(provider) if provider else None

    async def evaluate(self, context: Mapping[str, Any] | Any) -> RiskAssessment:
        data = _data(context)
        rules = self.rule_engine.evaluate(data)
        if rules.decision == RiskDecision.BLOCK:
            return RiskAssessment(
                decision=RiskDecision.BLOCK,
                risk_score=rules.risk_score,
                reasons=rules.matched_rules,
                matched_policy_categories=rules.matched_rules,
            )
        if not rules.uncertain_categories:
            return RiskAssessment(decision=RiskDecision.ALLOW, risk_score=0.0)
        if self.llm is None:
            # Uncertainty without an available semantic reviewer is fail closed
            # for automation but remains eligible for the human review queue.
            return RiskAssessment(
                decision=RiskDecision.REVIEW,
                risk_score=0.5,
                reasons=list(
                    dict.fromkeys(["SEMANTIC_RISK_REQUIRES_REVIEW", *rules.uncertain_categories])
                ),
                matched_policy_categories=rules.uncertain_categories,
                required_actions=["HUMAN_REVIEW"],
            )
        try:
            return await self.llm.evaluate(data)
        except (LLMProviderError, StructuredOutputError, TimeoutError):
            return RiskAssessment(
                decision=RiskDecision.REVIEW,
                risk_score=1.0,
                reasons=["RISK_AGENT_UNAVAILABLE_FAIL_CLOSED"],
                required_actions=["HUMAN_REVIEW"],
            )


__all__ = [
    "LLMRiskAgent",
    "RiskAgent",
    "RiskAssessment",
    "RuleRiskEngine",
    "RuleRiskResult",
]
