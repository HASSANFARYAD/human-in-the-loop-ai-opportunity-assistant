"""phase 4 5 6 foundations

Revision ID: 20260525_0001
Revises:
Create Date: 2026-05-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260525_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("ai_generations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), nullable=True), sa.Column("provider", sa.Text()), sa.Column("model", sa.Text()), sa.Column("task_type", sa.Text(), nullable=False, server_default="general"), sa.Column("prompt_version", sa.Text()), sa.Column("prompt_hash", sa.Text()), sa.Column("input_tokens", sa.Integer(), server_default="0"), sa.Column("output_tokens", sa.Integer(), server_default="0"), sa.Column("estimated_cost", sa.Float(), server_default="0"), sa.Column("latency_ms", sa.Integer()), sa.Column("status", sa.Text(), nullable=False, server_default="unknown"), sa.Column("error_message", sa.Text()), sa.Column("created_at", sa.Text(), nullable=False))
    op.create_table("prompt_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.Text(), nullable=False), sa.Column("version", sa.Text(), nullable=False), sa.Column("description", sa.Text()), sa.Column("template", sa.Text(), nullable=False), sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.Text(), nullable=False), sa.Column("updated_at", sa.Text(), nullable=False), sa.UniqueConstraint("name", "version"))
    op.create_table("automation_rules", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), nullable=False), sa.Column("name", sa.Text(), nullable=False), sa.Column("trigger_event", sa.Text(), nullable=False), sa.Column("action_type", sa.Text(), nullable=False), sa.Column("conditions_json", sa.Text()), sa.Column("action_config_json", sa.Text()), sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"), sa.Column("human_approval_required", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.Text(), nullable=False), sa.Column("updated_at", sa.Text(), nullable=False))
    op.create_table("automation_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("rule_id", sa.Integer(), nullable=True), sa.Column("user_id", sa.Integer(), nullable=False), sa.Column("status", sa.Text(), nullable=False, server_default="pending"), sa.Column("trigger_event", sa.Text(), nullable=False), sa.Column("input_payload", sa.Text()), sa.Column("output_payload", sa.Text()), sa.Column("error_message", sa.Text()), sa.Column("started_at", sa.Text()), sa.Column("completed_at", sa.Text()), sa.Column("created_at", sa.Text(), nullable=False))
    op.create_table("automation_steps", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), nullable=False), sa.Column("step_name", sa.Text(), nullable=False), sa.Column("status", sa.Text(), nullable=False, server_default="pending"), sa.Column("output_json", sa.Text()), sa.Column("error_message", sa.Text()), sa.Column("started_at", sa.Text()), sa.Column("completed_at", sa.Text()), sa.Column("created_at", sa.Text(), nullable=False))
    op.create_table("automation_errors", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), nullable=True), sa.Column("user_id", sa.Integer(), nullable=True), sa.Column("error_type", sa.Text()), sa.Column("error_message", sa.Text(), nullable=False), sa.Column("metadata_json", sa.Text()), sa.Column("created_at", sa.Text(), nullable=False))


def downgrade() -> None:
    for table in ["automation_errors", "automation_steps", "automation_runs", "automation_rules", "prompt_versions", "ai_generations"]:
        op.drop_table(table)
