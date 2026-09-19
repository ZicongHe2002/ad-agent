from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, enum_type
from app.domain.enums import UserRole, UserStatus


class User(AggregateMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="tenant_email"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("length(trim(display_name)) > 0", name="display_name_nonempty"),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        enum_type(UserRole), nullable=False, default=UserRole.VIEWER, server_default="VIEWER"
    )
    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus), nullable=False, default=UserStatus.ACTIVE, server_default="ACTIVE"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE
