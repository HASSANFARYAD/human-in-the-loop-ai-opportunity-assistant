"""make core resources workspace aware

Revision ID: 20260525_0003
Revises: 20260525_0002
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "20260525_0003"
down_revision = "20260525_0002"
branch_labels = None
depends_on = None


def _add_scope_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(sa.Column("workspace_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))


def upgrade() -> None:
    for table_name in [
        "jobs",
        "feedback",
        "integration_settings",
        "provider_configs",
        "ai_generations",
        "automation_rules",
        "automation_runs",
        "automation_errors",
    ]:
        _add_scope_columns(table_name)

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("base_content", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "post_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("provider_name", sa.Text()),
        sa.Column("transformed_content", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("published_url", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("post_targets")
    op.drop_table("posts")
    for table_name in [
        "automation_errors",
        "automation_runs",
        "automation_rules",
        "ai_generations",
        "provider_configs",
        "integration_settings",
        "feedback",
        "jobs",
    ]:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("organization_id")
            batch_op.drop_column("workspace_id")
