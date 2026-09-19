"""Concrete, source-verifiable post-anchor extraction."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, Field

from ..prompts import PromptLoader
from .provider import LLMMessage, LLMProvider, MessageRole
from .structured_output import generate_structured


class AnchorType(str, Enum):
    OBJECT = "OBJECT"
    COLOR = "COLOR"
    STYLE = "STYLE"
    TOPIC = "TOPIC"
    QUOTE = "QUOTE"
    ACTION = "ACTION"
    CLAIM = "CLAIM"


class AnchorCandidate(BaseModel):
    anchor_type: AnchorType
    anchor_text: str = Field(min_length=1, max_length=160)
    source_field: str
    confidence: float = Field(ge=0.0, le=1.0)


class AnchorExtractionPayload(BaseModel):
    anchors: list[AnchorCandidate] = Field(default_factory=list, max_length=5)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


class PostAnchor(BaseModel):
    id: UUID
    anchor_type: AnchorType
    anchor_text: str
    source_field: str
    confidence: float = Field(ge=0.0, le=1.0)


class AnchorExtractionResult(BaseModel):
    anchors: list[PostAnchor] = Field(default_factory=list, max_length=5)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    low_confidence: bool
    reason: str
    prompt_version: str
    prompt_hash: str
    model_provider: str
    model_name: str


_COLOR_WORDS = (
    "黑色",
    "白色",
    "灰色",
    "红色",
    "蓝色",
    "绿色",
    "黄色",
    "紫色",
    "粉色",
    "橙色",
    "棕色",
    "black",
    "white",
    "gray",
    "grey",
    "red",
    "blue",
    "green",
    "yellow",
    "purple",
    "pink",
    "orange",
    "brown",
)
_STYLE_WORDS = (
    "复古",
    "极简",
    "通勤",
    "休闲",
    "运动",
    "街头",
    "层次",
    "剪裁",
    "版型",
    "搭配",
    "vintage",
    "minimal",
    "casual",
    "sporty",
    "streetwear",
    "layered",
    "tailored",
    "silhouette",
)
_ACTION_WORDS = (
    "穿",
    "搭",
    "试",
    "展示",
    "走",
    "跑",
    "做",
    "制作",
    "开箱",
    "分享",
    "wear",
    "style",
    "show",
    "make",
    "unbox",
    "run",
    "walk",
)
_QUOTE_RE = re.compile(r"[“\"「『](.{2,60}?)[”\"」』]")
_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        return {"caption": value}
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if hasattr(value, "dict"):
        return dict(value.dict())
    return {
        name: getattr(value, name)
        for name in (
            "title",
            "caption",
            "hashtags",
            "mentions",
            "ocr_text",
            "transcript",
            "visual_summary",
            "external_post_id",
        )
        if hasattr(value, name)
    }


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _supported(anchor_text: str, source_value: Any) -> bool:
    if isinstance(source_value, (list, tuple, set)):
        haystack = " ".join(str(item).lstrip("#@") for item in source_value)
    else:
        haystack = str(source_value or "")
    needle = _normalized(anchor_text).lstrip("#@")
    return bool(needle) and needle in _normalized(haystack).lstrip("#@")


def _anchor_id(post_id: str, candidate: AnchorCandidate) -> UUID:
    material = f"{post_id}|{candidate.anchor_type.value}|{_normalized(candidate.anchor_text)}|{candidate.source_field}"
    return uuid5(NAMESPACE_URL, material)


def _candidate(
    anchor_type: AnchorType, text: str, field: str, confidence: float
) -> AnchorCandidate:
    return AnchorCandidate(
        anchor_type=anchor_type, anchor_text=text.strip(), source_field=field, confidence=confidence
    )


class AnchorExtractor:
    def __init__(
        self, provider: LLMProvider | None = None, *, prompt_loader: PromptLoader | None = None
    ) -> None:
        self.provider = provider
        self.prompt_loader = prompt_loader or PromptLoader()

    def _rule_extract(self, fields: Mapping[str, Any]) -> AnchorExtractionPayload:
        found: list[AnchorCandidate] = []
        for tag in fields.get("hashtags") or ():
            cleaned = str(tag).strip().lstrip("#")
            if cleaned:
                found.append(_candidate(AnchorType.TOPIC, cleaned, "hashtags", 0.98))
        textual_fields = ("title", "caption", "ocr_text", "transcript", "visual_summary")
        for field in textual_fields:
            text = str(fields.get(field) or "").strip()
            if not text:
                continue
            for quoted in _QUOTE_RE.findall(text):
                found.append(_candidate(AnchorType.QUOTE, quoted, field, 0.96))
            lowered = text.casefold()
            for color in _COLOR_WORDS:
                if color.casefold() in lowered:
                    found.append(_candidate(AnchorType.COLOR, color, field, 0.92))
            for style in _STYLE_WORDS:
                if style.casefold() in lowered:
                    found.append(_candidate(AnchorType.STYLE, style, field, 0.88))
            for segment in _SPLIT_RE.split(text):
                segment = segment.strip(" ,，。.!！?？")
                if len(segment) < 4:
                    continue
                clipped = segment[:60]
                anchor_type = (
                    AnchorType.ACTION
                    if any(word.casefold() in clipped.casefold() for word in _ACTION_WORDS)
                    else AnchorType.TOPIC
                )
                found.append(
                    _candidate(
                        anchor_type, clipped, field, 0.76 if field in {"title", "caption"} else 0.68
                    )
                )
                break
        unique: list[AnchorCandidate] = []
        seen = set()
        for item in sorted(found, key=lambda value: value.confidence, reverse=True):
            key = (item.anchor_type.value, _normalized(item.anchor_text))
            if key in seen or not _supported(item.anchor_text, fields.get(item.source_field)):
                continue
            seen.add(key)
            unique.append(item)
            if len(unique) == 5:
                break
        confidence = max((item.confidence for item in unique), default=0.0)
        return AnchorExtractionPayload(
            anchors=unique,
            overall_confidence=confidence,
            reason="Concrete source text found"
            if unique
            else "No concrete source-supported anchor",
        )

    async def extract(
        self,
        post: Any = None,
        *,
        title: str | None = None,
        caption: str | None = None,
        hashtags: Sequence[str] | None = None,
        mentions: Sequence[str] | None = None,
        ocr_text: str | None = None,
        transcript: str | None = None,
        visual_summary: str | None = None,
    ) -> AnchorExtractionResult:
        fields = _mapping(post)
        overrides = {
            "title": title,
            "caption": caption,
            "hashtags": hashtags,
            "mentions": mentions,
            "ocr_text": ocr_text,
            "transcript": transcript,
            "visual_summary": visual_summary,
        }
        fields.update({key: value for key, value in overrides.items() if value is not None})
        artifact = self.prompt_loader.load("anchor_extract")
        provider_name = "rules"
        model_name = "concrete-anchor-rules-v1"
        if self.provider is None:
            payload = self._rule_extract(fields)
        else:
            context = {
                key: fields.get(key)
                for key in (
                    "title",
                    "caption",
                    "hashtags",
                    "mentions",
                    "ocr_text",
                    "transcript",
                    "visual_summary",
                )
            }
            result = await generate_structured(
                self.provider,
                [
                    LLMMessage(role=MessageRole.SYSTEM, content=artifact.content),
                    LLMMessage(
                        role=MessageRole.USER,
                        content=json.dumps(context, ensure_ascii=False, default=str),
                    ),
                ],
                response_model=AnchorExtractionPayload,
                timeout_seconds=getattr(self.provider, "timeout_seconds", 0.5),
                metadata={
                    "prompt_name": artifact.name,
                    "prompt_version": artifact.version,
                    "prompt_hash": artifact.sha256,
                },
            )
            payload = result.value
            provider_name = result.response.provider
            model_name = result.response.model
        supported: list[AnchorCandidate] = []
        seen = set()
        for item in payload.anchors[:5]:
            if item.source_field not in fields or not _supported(
                item.anchor_text, fields.get(item.source_field)
            ):
                continue
            key = (item.anchor_type.value, _normalized(item.anchor_text))
            if key in seen:
                continue
            seen.add(key)
            supported.append(item)
        post_id = str(
            fields.get("external_post_id")
            or fields.get("id")
            or json.dumps(fields, ensure_ascii=False, sort_keys=True, default=str)
        )
        anchors = [
            PostAnchor(
                id=_anchor_id(post_id, item),
                anchor_type=item.anchor_type,
                anchor_text=item.anchor_text,
                source_field=item.source_field,
                confidence=item.confidence,
            )
            for item in supported
        ]
        confidence = min(
            1.0,
            max(
                0.0,
                min(
                    payload.overall_confidence,
                    max((item.confidence for item in supported), default=0.0),
                ),
            ),
        )
        low = not anchors or confidence < 0.6
        reason = (
            payload.reason
            if anchors
            else "No model anchor was verifiably present in its declared source field"
        )
        return AnchorExtractionResult(
            anchors=anchors,
            overall_confidence=confidence,
            low_confidence=low,
            reason=reason,
            prompt_version=artifact.version,
            prompt_hash=artifact.sha256,
            model_provider=provider_name,
            model_name=model_name,
        )


ConcreteAnchorExtractor = AnchorExtractor


__all__ = [
    "AnchorCandidate",
    "AnchorExtractionPayload",
    "AnchorExtractionResult",
    "AnchorExtractor",
    "AnchorType",
    "ConcreteAnchorExtractor",
    "PostAnchor",
]
