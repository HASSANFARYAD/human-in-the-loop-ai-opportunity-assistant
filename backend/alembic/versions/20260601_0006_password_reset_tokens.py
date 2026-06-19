"""add password reset tokens

Revision ID: 20260601_0006
Revises: 20260525_0005
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260601_0006"
down_revision = "20260525_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("consumed_at", sa.Text()),
        sa.Column("ip_address", sa.Text()),
        sa.Column("user_agent", sa.Text()),
    )
    op.create_index("idx_password_reset_tokens_user_time", "password_reset_tokens", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_password_reset_tokens_user_time", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
