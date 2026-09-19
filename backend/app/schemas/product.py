from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.enums import ClaimStatus

from .common import APIModel, TimestampedRead


class ProductBase(APIModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=100)
    material: str | None = None
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    approved_claims: list[dict[str, Any]] = Field(default_factory=list)
    forbidden_claims: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_price_range(self) -> ProductBase:
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min must not exceed price_max")
        return self


class ProductCreate(ProductBase):
    brand_id: UUID


class ProductUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    material: str | None = None
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    approved_claims: list[dict[str, Any]] | None = None
    forbidden_claims: list[dict[str, Any]] | None = None
    active: bool | None = None


class ProductRead(TimestampedRead, ProductBase):
    brand_id: UUID
    active: bool


class ProductClaimCreate(APIModel):
    product_id: UUID
    claim_text: str = Field(min_length=1)
    evidence: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None


class ProductClaimRead(TimestampedRead):
    product_id: UUID
    claim_text: str
    evidence: dict[str, Any]
    status: ClaimStatus
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    expires_at: datetime | None
    active: bool
