"""add sqlite friendly usage counters

Revision ID: 20260525_0004
Revises: 20260525_0003
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "20260525_0004"
down_revision = "20260525_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_counters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_start", sa.Text(), nullable=False),
        sa.Column("window_end", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("user_id", "ip_address", "resource_type", "window_start", name="uq_usage_counters_window"),
    )
    op.create_index("idx_usage_counters_window", "usage_counters", ["resource_type", "window_end"])


def downgrade() -> None:
    op.drop_index("idx_usage_counters_window", table_name="usage_counters")
    op.drop_table("usage_counters")
