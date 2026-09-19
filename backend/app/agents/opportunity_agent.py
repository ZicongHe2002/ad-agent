"""Opportunity scoring with server-owned arithmetic and hard-rule overrides."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from ..domain.enums import CommentStrategy, CreatorRelationship
from ..prompts import PromptLoader
from .provider import LLMMessage, LLMProvider, MessageRole
from .structured_output import generate_structured


class OpportunityDecision(str, Enum):
    HIGH_PRIORITY_CANDIDATE = "HIGH_PRIORITY_CANDIDATE"
    REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
    SLOW_PATH_OR_SKIP = "SLOW_PATH_OR_SKIP"
    SKIP = "SKIP"


class OpportunityComponents(BaseModel):
    creator_value: float = Field(ge=0.0, le=100.0)
    relevance: float = Field(ge=0.0, le=100.0)
    audience_match: float = Field(ge=0.0, le=100.0)
    traffic_potential: float = Field(ge=0.0, le=100.0)
    post_velocity: float = Field(ge=0.0, le=100.0)
    brand_fit: float = Field(ge=0.0, le=100.0)
    commercial_risk: float = Field(ge=0.0, le=100.0)
    platform_risk: float = Field(ge=0.0, le=100.0)


class OpportunityModelOutput(OpportunityComponents):
    # Accepted for provider schema compatibility, but never trusted.
    final_score: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    recommended_strategy: CommentStrategy = CommentStrategy.NORMAL_INTERACTION


class OpportunityScore(OpportunityComponents):
    final_score: float = Field(ge=0.0, le=100.0)
    reason_codes: list[str] = Field(default_factory=list)
    recommended_strategy: CommentStrategy
    decision: OpportunityDecision
    relationship_multiplier: float
    hard_blocked: bool = False
    prompt_version: str = "v1"
    prompt_hash: str = ""
    model_provider: str = "rules"
    model_name: str = "opportunity-rules-v1"


RELATIONSHIP_MULTIPLIERS: dict[CreatorRelationship, float] = {
    CreatorRelationship.OWN_ACCOUNT: 1.10,
    CreatorRelationship.PARTNER_CREATOR: 1.05,
    CreatorRelationship.OFFICIAL_CAMPAIGN_CREATOR: 1.05,
    CreatorRelationship.GENERAL_CREATOR: 0.90,
    CreatorRelationship.BRAND_ACCOUNT: 0.70,
    CreatorRelationship.COMPETITOR: 0.00,
    CreatorRelationship.BLOCKED_CREATOR: 0.00,
}


def clamp_score(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return min(100.0, max(0.0, number))


def relationship_multiplier(relationship: CreatorRelationship | str) -> float:
    parsed = (
        relationship
        if isinstance(relationship, CreatorRelationship)
        else CreatorRelationship(str(relationship).upper())
    )
    return RELATIONSHIP_MULTIPLIERS[parsed]


def calculate_opportunity_score(
    *,
    creator_value: Any,
    relevance: Any,
    audience_match: Any,
    traffic_potential: Any,
    post_velocity: Any,
    brand_fit: Any,
    commercial_risk: Any,
    platform_risk: Any,
    relationship: CreatorRelationship | str,
) -> float:
    """Apply the exact documented formula, multiplier, and final clamp."""

    values = {
        "creator_value": clamp_score(creator_value),
        "relevance": clamp_score(relevance),
        "audience_match": clamp_score(audience_match),
        "traffic_potential": clamp_score(traffic_potential),
        "post_velocity": clamp_score(post_velocity),
        "brand_fit": clamp_score(brand_fit),
        "commercial_risk": clamp_score(commercial_risk),
        "platform_risk": clamp_score(platform_risk),
    }
    base = (
        0.18 * values["creator_value"]
        + 0.22 * values["relevance"]
        + 0.15 * values["audience_match"]
        + 0.12 * values["traffic_potential"]
        + 0.08 * values["post_velocity"]
        + 0.15 * values["brand_fit"]
        - 0.05 * values["commercial_risk"]
        - 0.05 * values["platform_risk"]
    )
    return round(clamp_score(base * relationship_multiplier(relationship)), 6)


def opportunity_decision(score: float) -> OpportunityDecision:
    if score >= 80.0:
        return OpportunityDecision.HIGH_PRIORITY_CANDIDATE
    if score >= 65.0:
        return OpportunityDecision.REVIEW_CANDIDATE
    if score >= 45.0:
        return OpportunityDecision.SLOW_PATH_OR_SKIP
    return OpportunityDecision.SKIP


def _data(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if hasattr(value, "dict"):
        return dict(value.dict())
    return dict(vars(value)) if hasattr(value, "__dict__") else {}


def _relationship(creator: Any, explicit: CreatorRelationship | str | None) -> CreatorRelationship:
    value: Any = explicit
    if value is None:
        data = _data(creator)
        value = data.get(
            "relationship_type", data.get("relationship", CreatorRelationship.GENERAL_CREATOR)
        )
    if isinstance(value, CreatorRelationship):
        return value
    return CreatorRelationship(str(value).upper())


def _terms(value: Any) -> set[str]:
    text = (
        json.dumps(_data(value), ensure_ascii=False, default=str)
        if not isinstance(value, str)
        else value
    )
    return {item.casefold() for item in re.findall(r"[\w\u4e00-\u9fff]{2,}", text)}


def _safe_strategy(strategy: CommentStrategy, relationship: CreatorRelationship) -> CommentStrategy:
    partner_only = {
        CommentStrategy.LIGHT_BRAND_MENTION,
        CommentStrategy.PARTNER_BRAND_COMMENT,
        CommentStrategy.CAMPAIGN_DISCLOSURE,
    }
    if strategy in partner_only and relationship not in {
        CreatorRelationship.OWN_ACCOUNT,
        CreatorRelationship.PARTNER_CREATOR,
        CreatorRelationship.OFFICIAL_CAMPAIGN_CREATOR,
    }:
        return CommentStrategy.NORMAL_INTERACTION
    return strategy


class OpportunityAgent:
    def __init__(
        self, provider: LLMProvider | None = None, *, prompt_loader: PromptLoader | None = None
    ) -> None:
        self.provider = provider
        self.prompt_loader = prompt_loader or PromptLoader()

    def _heuristic_components(
        self,
        *,
        post: Any,
        creator: Any,
        campaign: Any,
        anchors: Sequence[Any],
    ) -> OpportunityModelOutput:
        creator_data = _data(creator)
        campaign_data = _data(campaign)
        priority = clamp_score(creator_data.get("priority", 50))
        post_terms = _terms(post)
        campaign_terms = _terms(campaign)
        overlap = len(post_terms & campaign_terms)
        relevance = min(100.0, 45.0 + overlap * 12.0 + min(len(anchors), 5) * 5.0)
        active = bool(campaign_data.get("active", True))
        return OpportunityModelOutput(
            creator_value=priority,
            relevance=relevance if active else 0.0,
            audience_match=65.0 if overlap else 45.0,
            traffic_potential=clamp_score(creator_data.get("traffic_potential", 50)),
            post_velocity=clamp_score(_data(post).get("post_velocity", 50)),
            brand_fit=min(100.0, relevance + 5.0),
            commercial_risk=20.0,
            platform_risk=20.0,
            reason_codes=["RULE_HEURISTIC", "CONCRETE_ANCHORS" if anchors else "NO_ANCHORS"],
            recommended_strategy=CommentStrategy.NORMAL_INTERACTION,
        )

    async def evaluate(
        self,
        *,
        post: Any = None,
        creator: Any = None,
        campaign: Any = None,
        anchors: Sequence[Any] = (),
        relationship: CreatorRelationship | str | None = None,
        components: OpportunityComponents | Mapping[str, Any] | None = None,
        hard_block_reasons: Sequence[str] = (),
        **component_overrides: Any,
    ) -> OpportunityScore:
        artifact = self.prompt_loader.load("opportunity_score")
        relation = _relationship(creator, relationship)
        model_provider = "rules"
        model_name = "opportunity-rules-v1"
        if components is not None:
            raw = (
                components.model_dump()
                if hasattr(components, "model_dump")
                else (components.dict() if hasattr(components, "dict") else dict(components))
            )
            raw.update(component_overrides)
            output = OpportunityModelOutput(**raw)
        elif component_overrides:
            output = OpportunityModelOutput(**component_overrides)
        elif self.provider is None:
            output = self._heuristic_components(
                post=post, creator=creator, campaign=campaign, anchors=anchors
            )
        else:
            context = {
                "post": _data(post),
                "creator": _data(creator),
                "campaign": _data(campaign),
                "anchors": [_data(item) for item in anchors],
                "relationship": relation.value,
            }
            generated = await generate_structured(
                self.provider,
                [
                    LLMMessage(role=MessageRole.SYSTEM, content=artifact.content),
                    LLMMessage(
                        role=MessageRole.USER,
                        content=json.dumps(context, ensure_ascii=False, default=str),
                    ),
                ],
                response_model=OpportunityModelOutput,
                timeout_seconds=getattr(self.provider, "timeout_seconds", 0.9),
                metadata={
                    "prompt_name": artifact.name,
                    "prompt_version": artifact.version,
                    "prompt_hash": artifact.sha256,
                },
            )
            output = generated.value
            model_provider = generated.response.provider
            model_name = generated.response.model
        values = {
            field: clamp_score(getattr(output, field))
            for field in OpportunityComponents.__annotations__
        }
        hard_reasons = list(hard_block_reasons)
        if relation in {CreatorRelationship.COMPETITOR, CreatorRelationship.BLOCKED_CREATOR}:
            hard_reasons.append(f"RELATIONSHIP_{relation.value}")
        campaign_data = _data(campaign)
        if campaign_data and not bool(campaign_data.get("active", True)):
            hard_reasons.append("CAMPAIGN_INACTIVE")
        score = calculate_opportunity_score(**values, relationship=relation)
        if hard_reasons:
            score = 0.0
        reason_codes = list(dict.fromkeys([*output.reason_codes, *hard_reasons]))
        return OpportunityScore(
            **values,
            final_score=score,
            reason_codes=reason_codes,
            recommended_strategy=CommentStrategy.SKIP
            if hard_reasons
            else _safe_strategy(output.recommended_strategy, relation),
            decision=OpportunityDecision.SKIP if hard_reasons else opportunity_decision(score),
            relationship_multiplier=relationship_multiplier(relation),
            hard_blocked=bool(hard_reasons),
            prompt_version=artifact.version,
            prompt_hash=artifact.sha256,
            model_provider=model_provider,
            model_name=model_name,
        )


__all__ = [
    "RELATIONSHIP_MULTIPLIERS",
    "OpportunityAgent",
    "OpportunityComponents",
    "OpportunityDecision",
    "OpportunityModelOutput",
    "OpportunityScore",
    "calculate_opportunity_score",
    "clamp_score",
    "opportunity_decision",
    "relationship_multiplier",
]
