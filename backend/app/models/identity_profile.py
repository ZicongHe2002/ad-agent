from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, enum_type
from app.domain.enums import AccountKind


class AccountIdentityProfile(AggregateMixin, Base):
    __tablename__ = "account_identity_profiles"
    __table_args__ = (
        CheckConstraint(
            "length(trim(legal_or_operating_entity)) > 0",
            name="entity_nonempty",
        ),
        CheckConstraint(
            "length(trim(public_identity_text)) > 0",
            name="public_identity_nonempty",
        ),
        CheckConstraint(
            "NOT (account_kind = 'BRAND_OFFICIAL' AND may_speak_as_consumer)",
            name="brand_not_consumer",
        ),
        CheckConstraint(
            "NOT (account_kind = 'BRAND_OFFICIAL' AND may_use_first_person_experience)",
            name="brand_no_first_person_experience",
        ),
        CheckConstraint(
            "NOT may_use_first_person_experience OR (approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="experience_requires_human_approval",
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    legal_or_operating_entity: Mapped[str] = mapped_column(String(255), nullable=False)
    account_kind: Mapped[AccountKind] = mapped_column(enum_type(AccountKind), nullable=False)
    public_identity_text: Mapped[str] = mapped_column(Text, nullable=False)
    may_speak_as_consumer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    may_use_first_person_experience: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    requires_brand_disclosure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    requires_ai_disclosure_policy_check: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
