from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import RiskDecision


class RiskEvent(AggregateMixin, Base):
    __tablename__ = "risk_events"
    __table_args__ = (
        CheckConstraint("risk_score BETWEEN 0 AND 1", name="risk_score_range"),
        CheckConstraint(
            "NOT (rule_decision = 'BLOCK' AND final_decision != 'BLOCK')",
            name="hard_rule_block_not_overridden",
        ),
    )

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("comment_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_decision: Mapped[RiskDecision] = mapped_column(
        enum_type(RiskDecision, name="rule_risk_decision_enum"), nullable=False
    )
    llm_decision: Mapped[RiskDecision | None] = mapped_column(
        enum_type(RiskDecision, name="llm_risk_decision_enum")
    )
    final_decision: Mapped[RiskDecision] = mapped_column(
        enum_type(RiskDecision, name="final_risk_decision_enum"), nullable=False
    )
    risk_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    matched_rules: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    reasons: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    policy_versions: Mapped[dict[str, str]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
