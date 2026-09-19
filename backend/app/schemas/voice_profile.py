from __future__ import annotations

from uuid import UUID

from pydantic import Field

from .common import APIModel, TimestampedRead


class VoiceProfileCreate(APIModel):
    brand_id: UUID
    name: str = Field(min_length=1, max_length=100)
    tone_attributes: list[str] = Field(default_factory=list)
    preferred_sentence_length: str = Field(default="SHORT", min_length=1, max_length=30)
    emoji_policy: dict[str, object] = Field(default_factory=dict)
    allowed_phrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    approved_examples: list[str] = Field(default_factory=list)


class VoiceProfileRead(TimestampedRead, VoiceProfileCreate):
    version: int = Field(gt=0)
    active: bool
