from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PublishingSettings(TimestampMixin, Base):
    """Workspace publishing policy, shared by the API and every worker."""

    __tablename__ = "publishing_settings"
    __table_args__ = (CheckConstraint("mode IN ('REVIEW', 'AUTO')", name="valid_mode"),)

    scope_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="REVIEW", server_default="REVIEW")
    auto_disclosure_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

