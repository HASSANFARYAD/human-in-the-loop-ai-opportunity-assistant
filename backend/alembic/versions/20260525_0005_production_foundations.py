"""add production foundation tables

Revision ID: 20260525_0005
Revises: 20260525_0004
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "20260525_0005"
down_revision = "20260525_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("metric_type", sa.Text(), nullable=False, server_default="counter"),
        sa.Column("value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("labels_json", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_system_metrics_name_time", "system_metrics", ["metric_name", "created_at"])
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("severity", sa.Text(), nullable=False, server_default="warning"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("source", sa.Text(), nullable=False, server_default="system"),
        sa.Column("metadata_json", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("acknowledged_at", sa.Text()),
    )
    op.create_index("idx_alert_events_status_time", "alert_events", ["status", "created_at"])
    op.create_table(
        "worker_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("queue_name", sa.Text(), nullable=False, server_default="default"),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("locked_at", sa.Text()),
        sa.Column("locked_by", sa.Text()),
        sa.Column("run_after", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text()),
    )
    op.create_index("idx_worker_jobs_ready", "worker_jobs", ["status", "queue_name", "run_after"])
    op.create_table(
        "compliance_exports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer()),
        sa.Column("export_type", sa.Text(), nullable=False, server_default="user_data"),
        sa.Column("status", sa.Text(), nullable=False, server_default="completed"),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("compliance_exports")
    op.drop_index("idx_worker_jobs_ready", table_name="worker_jobs")
    op.drop_table("worker_jobs")
    op.drop_index("idx_alert_events_status_time", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index("idx_system_metrics_name_time", table_name="system_metrics")
    op.drop_table("system_metrics")
