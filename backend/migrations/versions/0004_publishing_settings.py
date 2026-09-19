"""Persist workspace review/automatic publishing policy.

Revision ID: 0004_publishing_settings
Revises: 0003_post_source_url
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_publishing_settings"
down_revision: str | None = "0003_post_source_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publishing_settings",
        sa.Column("scope_key", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.String(10), nullable=False, server_default="REVIEW"),
        sa.Column("auto_disclosure_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id"),
        sa.CheckConstraint("mode IN ('REVIEW', 'AUTO')", name="valid_mode"),
    )


def downgrade() -> None:
    op.drop_table("publishing_settings")
