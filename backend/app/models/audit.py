from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import ActorType


class AuditLog(AggregateMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("length(trim(action)) > 0", name="action_nonempty"),
        CheckConstraint("length(trim(resource_type)) > 0", name="resource_type_nonempty"),
        CheckConstraint(
            "actor_type != 'USER' OR actor_id IS NOT NULL",
            name="user_actor_has_id",
        ),
        Index("ix_audit_resource_created", "resource_type", "resource_id", "created_at"),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_type: Mapped[ActorType] = mapped_column(enum_type(ActorType), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(nullable=True)
    before: Mapped[dict[str, object] | None] = mapped_column(JSONType)
    after: Mapped[dict[str, object] | None] = mapped_column(JSONType)
    trace_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
