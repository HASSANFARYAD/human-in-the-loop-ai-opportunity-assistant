"""phase7 enterprise foundation

Revision ID: 20260525_0002
Revises: 20260525_0001
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "20260525_0002"
down_revision = "20260525_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("organization_id", "slug", name="uq_workspaces_org_slug"),
    )
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="viewer"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("invited_by", sa.Integer()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )
    op.create_table(
        "roles",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("description", sa.Text()),
        sa.Column("is_system", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "permissions",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_name", sa.Text(), nullable=False),
        sa.Column("permission_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("role_name", "permission_name"),
    )
    op.create_table(
        "shared_resources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=False),
        sa.Column("access_level", sa.Text(), nullable=False, server_default="read"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text()),
        sa.UniqueConstraint("workspace_id", "resource_type", "resource_id", name="uq_shared_resources_workspace_resource"),
    )
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("workspace_id", sa.Integer()))
        batch_op.add_column(sa.Column("organization_id", sa.Integer()))


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_column("organization_id")
        batch_op.drop_column("workspace_id")
    op.drop_table("shared_resources")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
    op.drop_table("organizations")
