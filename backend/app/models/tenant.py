from __future__ import annotations

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, enum_type
from app.domain.enums import TenantStatus


class Tenant(AggregateMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint("slug = lower(slug)", name="slug_lowercase"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    status: Mapped[TenantStatus] = mapped_column(
        enum_type(TenantStatus),
        nullable=False,
        default=TenantStatus.ACTIVE,
        server_default="ACTIVE",
    )
