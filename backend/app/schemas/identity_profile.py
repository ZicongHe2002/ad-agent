from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.enums import AccountKind

from .common import APIModel, TimestampedRead


class IdentityProfileCreate(APIModel):
    legal_or_operating_entity: str = Field(min_length=1, max_length=255)
    account_kind: AccountKind
    public_identity_text: str = Field(min_length=1)
    may_speak_as_consumer: bool = False
    may_use_first_person_experience: bool = False
    requires_brand_disclosure: bool = True
    requires_ai_disclosure_policy_check: bool = True

    @model_validator(mode="after")
    def brand_official_cannot_be_consumer(self) -> IdentityProfileCreate:
        if self.account_kind is AccountKind.BRAND_OFFICIAL and (
            self.may_speak_as_consumer or self.may_use_first_person_experience
        ):
            raise ValueError(
                "BRAND_OFFICIAL cannot speak as a consumer or claim personal experience"
            )
        return self


class IdentityProfileRead(TimestampedRead, IdentityProfileCreate):
    tenant_id: UUID | None
    active: bool
    approved_by_user_id: UUID | None
    approved_at: datetime | None
