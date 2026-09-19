"""Persist the original post URL for an explicit manual handoff.

Revision ID: 0003_post_source_url
Revises: 0002_disclosure_evidence
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_post_source_url"
down_revision = "0002_disclosure_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("source_url", sa.String(2048), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("posts") as batch:
        batch.drop_column("source_url")
