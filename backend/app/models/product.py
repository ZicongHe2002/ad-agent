from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import ClaimStatus


class Product(AggregateMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("brand_id", "name", name="product_brand_name"),
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint("price_min IS NULL OR price_min >= 0", name="price_min_nonnegative"),
        CheckConstraint("price_max IS NULL OR price_max >= 0", name="price_max_nonnegative"),
        CheckConstraint(
            "price_min IS NULL OR price_max IS NULL OR price_min <= price_max",
            name="price_range_order",
        ),
    )

    brand_id: Mapped[UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    material: Mapped[str | None] = mapped_column(Text)
    price_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    approved_claims: Mapped[list[dict[str, object]]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    forbidden_claims: Mapped[list[dict[str, object]]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class ProductClaim(AggregateMixin, Base):
    __tablename__ = "product_claims"
    __table_args__ = (
        UniqueConstraint("product_id", "claim_text", name="product_claim_text"),
        CheckConstraint("length(trim(claim_text)) > 0", name="claim_text_nonempty"),
        CheckConstraint(
            "status != 'APPROVED' OR (approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="approved_has_audit",
        ),
        CheckConstraint(
            "expires_at IS NULL OR approved_at IS NULL OR expires_at > approved_at",
            name="expiry_after_approval",
        ),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    status: Mapped[ClaimStatus] = mapped_column(
        enum_type(ClaimStatus), nullable=False, default=ClaimStatus.DRAFT, server_default="DRAFT"
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
