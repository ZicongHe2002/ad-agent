from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import CapabilityName, CapabilityStatus, Platform


class CapabilityRecord(AggregateMixin, Base):
    __tablename__ = "capability_records"
    __table_args__ = (
        UniqueConstraint("platform", "capability", name="platform_capability"),
        CheckConstraint(
            "status NOT IN ('SUPPORTED', 'CONDITIONAL') OR "
            "(verified_at IS NOT NULL AND source_title IS NOT NULL AND source_owner IS NOT NULL)",
            name="verified_status_has_evidence",
        ),
        CheckConstraint(
            "expires_at IS NULL OR verified_at IS NULL OR expires_at > verified_at",
            name="expiry_after_verification",
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    platform: Mapped[Platform] = mapped_column(enum_type(Platform), nullable=False)
    capability: Mapped[CapabilityName] = mapped_column(enum_type(CapabilityName), nullable=False)
    status: Mapped[CapabilityStatus] = mapped_column(
        enum_type(CapabilityStatus),
        nullable=False,
        default=CapabilityStatus.UNKNOWN,
        server_default="UNKNOWN",
    )
    source_title: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_owner: Mapped[str | None] = mapped_column(String(160))
    scope: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    conditions: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    limitations: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class CapabilitySnapshot(AggregateMixin, Base):
    __tablename__ = "capability_snapshots"
    __table_args__ = (
        UniqueConstraint("platform", "records_hash", name="platform_records_hash"),
        CheckConstraint("length(records_hash) = 64", name="records_hash_sha256"),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > captured_at", name="expiry_after_capture"
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    platform: Mapped[Platform] = mapped_column(enum_type(Platform), nullable=False)
    capabilities: Mapped[dict[str, str]] = mapped_column(JSONType, nullable=False)
    record_ids: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    records_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
