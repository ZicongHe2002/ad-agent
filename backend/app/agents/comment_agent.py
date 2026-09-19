"""Policy-constrained, anchor-grounded comment generation."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, Field

from ..domain.enums import CommentStrategy, ContentProvenance, CreatorRelationship, RunMode
from ..prompts import PromptLoader
from .provider import LLMMessage, LLMProvider, MessageRole
from .structured_output import generate_structured


class CommentGenerationError(ValueError):
    pass


class GeneratedComment(BaseModel):
    comment: str = Field(min_length=1, max_length=2_000)
    strategy: CommentStrategy
    referenced_anchor_ids: list[UUID] = Field(default_factory=list)
    referenced_claim_ids: list[UUID] = Field(default_factory=list)
    relevance_score: float = Field(ge=0.0, le=1.0)
    commercial_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    generation_reason: str
    uses_first_person_experience: bool = False
    implies_consumer_identity: bool = False

    @property
    def text(self) -> str:
        return self.comment


class GeneratedCommentPayload(BaseModel):
    candidates: list[GeneratedComment] = Field(min_length=1, max_length=5)


class GeneratedCommentBatch(BaseModel):
    candidates: list[GeneratedComment]
    prompt_version: str
    prompt_hash: str
    model_provider: str
    model_name: str
    model_request_id: str | None = None
    content_provenance: ContentProvenance = ContentProvenance.AI_GENERATED_AUTO_APPROVED


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


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in value if character.isalnum())


def _uuid(value: Any, namespace: str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid5(NAMESPACE_URL, f"{namespace}:{value}")


def _anchors(values: Sequence[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        data = _data(value)
        text = data.get("anchor_text", data.get("text"))
        if not text:
            continue
        result.append(
            {
                "id": _uuid(data.get("id", f"anchor-{index}"), "anchor"),
                "text": str(text),
                "type": str(
                    getattr(
                        data.get("anchor_type", data.get("type", "TOPIC")),
                        "value",
                        data.get("anchor_type", data.get("type", "TOPIC")),
                    )
                ),
                "confidence": float(data.get("confidence", 1.0)),
            }
        )
    return result


def _approved_claims(*contexts: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for context in contexts:
        data = _data(context)
        candidates: list[Any] = []
        for key in ("approved_claims", "claims"):
            value = data.get(key)
            if isinstance(value, (list, tuple)):
                candidates.extend(value)
        for index, claim in enumerate(candidates):
            claim_data = _data(claim)
            if claim_data:
                status = str(
                    getattr(
                        claim_data.get("status", "APPROVED"),
                        "value",
                        claim_data.get("status", "APPROVED"),
                    )
                )
                if status.upper() != "APPROVED":
                    continue
                text = claim_data.get("claim_text", claim_data.get("text"))
                identifier = claim_data.get("id", f"{text}-{index}")
            else:
                text = str(claim)
                identifier = f"{text}-{index}"
            if text:
                result.append({"id": _uuid(identifier, "claim"), "text": str(text)})
    deduped: dict[UUID, dict[str, Any]] = {item["id"]: item for item in result}
    return list(deduped.values())


def _enum_value(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(getattr(value, "value", value)).upper()


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


class CommentAgent:
    def __init__(
        self, provider: LLMProvider | None = None, *, prompt_loader: PromptLoader | None = None
    ) -> None:
        self.provider = provider
        self.prompt_loader = prompt_loader or PromptLoader()

    @staticmethod
    def _prompt_name(strategy: CommentStrategy, campaign: Any) -> str:
        if strategy in {
            CommentStrategy.LIGHT_BRAND_MENTION,
            CommentStrategy.PARTNER_BRAND_COMMENT,
            CommentStrategy.CAMPAIGN_DISCLOSURE,
        }:
            return "comment_partner"
        mode = _enum_value(_data(campaign).get("run_mode"), RunMode.NORMAL.value)
        return (
            "comment_fast"
            if mode in {RunMode.FAST.value, RunMode.FIRST_COMMENT.value, RunMode.TOP5_COMMENT.value}
            else "comment_normal"
        )

    def _deterministic_candidates(
        self,
        *,
        anchors: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        strategy: CommentStrategy,
        brand: Any,
        account_identity: Any,
        campaign: Any,
        count: int,
    ) -> list[GeneratedComment]:
        brand_name = str(_data(brand).get("name", "品牌"))
        identity = _data(account_identity)
        identity_label = str(
            identity.get("display_name", identity.get("declared_identity", f"{brand_name}官方账号"))
        )
        disclosure = str(_data(campaign).get("disclosure_text", "合作品牌"))
        generation_variant = max(0, int(_data(campaign).get("generation_variant", 0) or 0))
        result: list[GeneratedComment] = []
        for index in range(count):
            anchor = anchors[index % len(anchors)]
            anchor_text = anchor["text"]
            is_zh = _contains_cjk(anchor_text + brand_name)
            wording_index = generation_variant * count + index
            claim_ids: list[UUID] = []
            templates: tuple[str, ...]
            if strategy == CommentStrategy.NORMAL_INTERACTION:
                templates = (
                    (
                        "{anchor}这个细节很有辨识度。",
                        "从{anchor}切入，整体表达更清楚了。",
                        "再看{anchor}，这个落点把内容的重点带出来了。",
                        "{anchor}这一处很具体，也让整段内容更有层次。",
                        "最先注意到的是{anchor}，它让主题一下变得清晰。",
                        "{anchor}没有被一笔带过，这个处理很耐看。",
                    )
                    if is_zh
                    else (
                        "The {anchor} detail gives this a clear point of view.",
                        "Starting with {anchor} makes the idea especially clear.",
                        "Looking again at {anchor}, that choice brings the main idea forward.",
                        "The specific {anchor} moment gives the whole post more structure.",
                        "What stands out first is {anchor}; it makes the theme immediately clear.",
                        "The treatment of {anchor} is specific without overexplaining it.",
                    )
                )
                text = templates[wording_index % len(templates)].format(anchor=anchor_text)
            elif strategy == CommentStrategy.EXPERT_COMMENT:
                templates = (
                    (
                        "{anchor}让整体层次更清楚，细节处理得很克制。",
                        "从{anchor}能看出结构安排，信息重点也更集中。",
                        "{anchor}的处理建立了清晰层次，没有抢走主题。",
                        "把{anchor}放在这里，前后的表达衔接得很自然。",
                    )
                    if is_zh
                    else (
                        "The {anchor} choice creates a clearer, restrained sense of structure.",
                        "The structure around {anchor} keeps the information focused.",
                        "The handling of {anchor} adds hierarchy without distracting from the theme.",
                        "Placing {anchor} here makes the surrounding ideas connect naturally.",
                    )
                )
                text = templates[wording_index % len(templates)].format(anchor=anchor_text)
            elif strategy == CommentStrategy.LIGHT_BRAND_MENTION:
                templates = (
                    (
                        "这里是{identity}，{anchor}这个观察让我们很有共鸣。",
                        "{identity}在这里明确回应：{anchor}的呈现很具体。",
                        "来自{identity}的公开留言：我们注意到了{anchor}这个细节。",
                    )
                    if is_zh
                    else (
                        "This is {identity}; the {anchor} detail resonates with our brand perspective.",
                        "A disclosed note from {identity}: the presentation of {anchor} is very specific.",
                        "Commenting openly as {identity}, we noticed the {anchor} detail.",
                    )
                )
                text = templates[wording_index % len(templates)].format(
                    identity=identity_label, anchor=anchor_text
                )
            elif strategy == CommentStrategy.PARTNER_BRAND_COMMENT:
                templates = (
                    (
                        "作为{disclosure}，我们很喜欢你对{anchor}的具体呈现。",
                        "公开说明我们是{disclosure}：{anchor}这个细节表达得很清楚。",
                        "以{disclosure}身份留言，{anchor}让这次内容更有层次。",
                    )
                    if is_zh
                    else (
                        "As {disclosure}, we appreciate the specific way you presented {anchor}.",
                        "Disclosing that we are {disclosure}: the {anchor} detail is presented clearly.",
                        "Commenting as {disclosure}, we found that {anchor} gives this post more structure.",
                    )
                )
                text = templates[wording_index % len(templates)].format(
                    disclosure=disclosure, anchor=anchor_text
                )
            elif strategy == CommentStrategy.CAMPAIGN_DISCLOSURE:
                templates = (
                    (
                        "{disclosure}：{anchor}正好回应了这次内容的主题。",
                        "{disclosure}说明：我们关注到{anchor}和本次主题的连接。",
                        "作为{disclosure}公开留言，{anchor}把主题落到了具体细节上。",
                    )
                    if is_zh
                    else (
                        "{disclosure}: {anchor} speaks directly to this campaign's theme.",
                        "{disclosure} note: we noticed how {anchor} connects with the campaign theme.",
                        "Commenting openly as {disclosure}, {anchor} grounds the theme in a specific detail.",
                    )
                )
                text = templates[wording_index % len(templates)].format(
                    disclosure=disclosure, anchor=anchor_text
                )
            elif strategy == CommentStrategy.PRODUCT_RELATED:
                if not claims:
                    raise CommentGenerationError(
                        "PRODUCT_RELATED requires at least one approved claim"
                    )
                claim = claims[index % len(claims)]
                claim_ids = [claim["id"]]
                templates = (
                    (
                        "{anchor}和“{claim}”这一已确认信息很契合。",
                        "围绕{anchor}，这里仅补充已批准信息：“{claim}”。",
                        "{anchor}对应到一个可核验的品牌事实：“{claim}”。",
                    )
                    if is_zh
                    else (
                        "The {anchor} detail connects with the approved fact: {claim}.",
                        "On {anchor}, we are adding only this approved fact: {claim}.",
                        "The {anchor} detail maps to a verifiable brand fact: {claim}.",
                    )
                )
                text = templates[wording_index % len(templates)].format(
                    anchor=anchor_text, claim=claim["text"]
                )
            else:
                raise CommentGenerationError("SKIP is not a generative comment strategy")
            result.append(
                GeneratedComment(
                    comment=text,
                    strategy=strategy,
                    referenced_anchor_ids=[anchor["id"]],
                    referenced_claim_ids=claim_ids,
                    relevance_score=0.92,
                    commercial_score=0.15
                    if strategy
                    in {CommentStrategy.NORMAL_INTERACTION, CommentStrategy.EXPERT_COMMENT}
                    else 0.55,
                    confidence=0.9,
                    generation_reason=f"Grounded in the supplied {anchor['type'].lower()} anchor",
                    uses_first_person_experience=False,
                    implies_consumer_identity=False,
                )
            )
        return result

    @staticmethod
    def _validate_candidates(
        candidates: Sequence[GeneratedComment],
        *,
        count: int,
        anchors: Sequence[dict[str, Any]],
        claims: Sequence[dict[str, Any]],
        recent_comments: Sequence[str],
        expected_strategy: CommentStrategy,
    ) -> list[GeneratedComment]:
        if len(candidates) != count:
            raise CommentGenerationError(
                f"Expected exactly {count} candidates, got {len(candidates)}"
            )
        anchor_by_id = {item["id"]: item for item in anchors}
        claim_by_id = {item["id"]: item for item in claims}
        claim_ids = set(claim_by_id)
        recent = {_normalize(value) for value in recent_comments}
        seen = set()
        result: list[GeneratedComment] = []
        for candidate in candidates:
            if candidate.strategy != expected_strategy:
                raise CommentGenerationError("Provider changed the requested strategy")
            if candidate.uses_first_person_experience or candidate.implies_consumer_identity:
                raise CommentGenerationError(
                    "Provider output implies prohibited consumer identity or experience"
                )
            if not candidate.referenced_anchor_ids:
                raise CommentGenerationError("Every candidate must reference a concrete anchor")
            if any(item not in anchor_by_id for item in candidate.referenced_anchor_ids):
                raise CommentGenerationError("Candidate referenced an unknown anchor")
            if not any(
                _normalize(anchor_by_id[item]["text"]) in _normalize(candidate.comment)
                for item in candidate.referenced_anchor_ids
            ):
                raise CommentGenerationError("Referenced anchor is not grounded in candidate text")
            if any(item not in claim_ids for item in candidate.referenced_claim_ids):
                raise CommentGenerationError("Candidate referenced an unapproved claim")
            if (
                candidate.strategy == CommentStrategy.PRODUCT_RELATED
                and not candidate.referenced_claim_ids
            ):
                raise CommentGenerationError(
                    "Product-related candidates must reference an approved claim"
                )
            if any(
                _normalize(claim_by_id[item]["text"]) not in _normalize(candidate.comment)
                for item in candidate.referenced_claim_ids
            ):
                raise CommentGenerationError("Referenced claim is not present in candidate text")
            normalized = _normalize(candidate.comment)
            if not normalized or normalized in seen or normalized in recent:
                raise CommentGenerationError("Generated candidate is an exact duplicate")
            seen.add(normalized)
            result.append(candidate)
        return result

    async def generate_comments(
        self,
        *,
        brand: Any,
        account_identity: Any,
        voice_profile: Any,
        campaign: Any,
        creator: Any,
        post: Any,
        anchors: Sequence[Any],
        strategy: CommentStrategy | str,
        recent_comments: Sequence[str],
        count: int = 2,
    ) -> GeneratedCommentBatch:
        if count < 1 or count > 5:
            raise ValueError("count must be between 1 and 5")
        if account_identity is None or not _data(account_identity):
            raise CommentGenerationError("Declared account identity is required")
        parsed_strategy = (
            strategy
            if isinstance(strategy, CommentStrategy)
            else CommentStrategy(str(strategy).upper())
        )
        if parsed_strategy == CommentStrategy.SKIP:
            raise CommentGenerationError("SKIP does not generate comments")
        anchor_values = _anchors(anchors)
        if not anchor_values:
            raise CommentGenerationError("At least one concrete anchor is required")
        relationship = _enum_value(
            _data(creator).get("relationship_type", _data(creator).get("relationship")),
            CreatorRelationship.GENERAL_CREATOR.value,
        )
        if parsed_strategy in {
            CommentStrategy.LIGHT_BRAND_MENTION,
            CommentStrategy.PARTNER_BRAND_COMMENT,
            CommentStrategy.CAMPAIGN_DISCLOSURE,
        } and relationship not in {
            CreatorRelationship.OWN_ACCOUNT.value,
            CreatorRelationship.PARTNER_CREATOR.value,
            CreatorRelationship.OFFICIAL_CAMPAIGN_CREATOR.value,
        }:
            raise CommentGenerationError(
                "Brand/partner strategies require an owned, partner, or official campaign creator"
            )
        claims = _approved_claims(brand, campaign, post)
        prompt_name = self._prompt_name(parsed_strategy, campaign)
        artifact = self.prompt_loader.load(prompt_name)
        request_id: str | None = None
        if self.provider is None:
            candidates = self._deterministic_candidates(
                anchors=anchor_values,
                claims=claims,
                strategy=parsed_strategy,
                brand=brand,
                account_identity=account_identity,
                campaign=campaign,
                count=count,
            )
            provider_name = "mock"
            model_name = "deterministic-comment-rules-v1"
        else:
            context = {
                "brand": _data(brand),
                "account_identity": _data(account_identity),
                "voice_profile": _data(voice_profile),
                "campaign": _data(campaign),
                "creator": _data(creator),
                "post": _data(post),
                "anchors": [{**item, "id": str(item["id"])} for item in anchor_values],
                "approved_claims": [{**item, "id": str(item["id"])} for item in claims],
                "strategy": parsed_strategy.value,
                "recent_comments": list(recent_comments),
                "count": count,
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
                response_model=GeneratedCommentPayload,
                timeout_seconds=getattr(self.provider, "timeout_seconds", 1.8),
                metadata={
                    "prompt_name": artifact.name,
                    "prompt_version": artifact.version,
                    "prompt_hash": artifact.sha256,
                    "candidate_count": count,
                },
            )
            candidates = generated.value.candidates
            provider_name = generated.response.provider
            model_name = generated.response.model
            request_id = generated.response.request_id
        validated = self._validate_candidates(
            candidates,
            count=count,
            anchors=anchor_values,
            claims=claims,
            recent_comments=recent_comments,
            expected_strategy=parsed_strategy,
        )
        return GeneratedCommentBatch(
            candidates=validated,
            prompt_version=artifact.version,
            prompt_hash=artifact.sha256,
            model_provider=provider_name,
            model_name=model_name,
            model_request_id=request_id,
        )


async def generate_comments(**kwargs: Any) -> GeneratedCommentBatch:
    provider = kwargs.pop("provider", None)
    prompt_loader = kwargs.pop("prompt_loader", None)
    return await CommentAgent(provider=provider, prompt_loader=prompt_loader).generate_comments(
        **kwargs
    )


__all__ = [
    "CommentAgent",
    "CommentGenerationError",
    "GeneratedComment",
    "GeneratedCommentBatch",
    "GeneratedCommentPayload",
    "generate_comments",
]
