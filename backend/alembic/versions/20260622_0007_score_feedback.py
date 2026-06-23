"""add score feedback

Revision ID: 20260622_0007
Revises: 20260601_0006
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20260622_0007"
down_revision = "20260601_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "score_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer()),
        sa.Column("job_id", sa.Integer()),
        sa.Column("signal", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_score_feedback_user_time", "score_feedback", ["user_id", "id"])


def downgrade() -> None:
    op.drop_index("idx_score_feedback_user_time", table_name="score_feedback")
    op.drop_table("score_feedback")
