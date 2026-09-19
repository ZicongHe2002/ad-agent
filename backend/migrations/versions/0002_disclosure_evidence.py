"""Persist explicit disclosure decisions and their reviewer evidence.

Revision ID: 0002_disclosure_evidence
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_disclosure_evidence"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("comment_candidates") as batch:
        batch.add_column(sa.Column(
            "disclosure_evidence",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False, server_default=sa.text("'{}'"),
        ))
        batch.add_column(sa.Column("disclosure_resolved_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("disclosure_resolved_by_user_id", sa.Uuid()))
        batch.create_foreign_key(
            "fk_comment_candidates_disclosure_resolved_by_user_id_users", "users",
            ["disclosure_resolved_by_user_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("comment_candidates") as batch:
        batch.drop_constraint(
            "fk_comment_candidates_disclosure_resolved_by_user_id_users", type_="foreignkey"
        )
        batch.drop_column("disclosure_resolved_by_user_id")
        batch.drop_column("disclosure_resolved_at")
        batch.drop_column("disclosure_evidence")
