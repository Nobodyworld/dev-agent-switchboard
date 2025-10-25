"""Add ExecPlan registry tables

Revision ID: 20250214_add_execplan_registry
Revises: 20240524_add_completed_notes
Create Date: 2025-02-14
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20250214_add_execplan_registry"
down_revision = "20240524_add_completed_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exec_plan_registry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("registry_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("source_etag", sa.String(length=128), nullable=True),
        sa.Column("extensions", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "exec_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_created_at", sa.DateTime(), nullable=True),
        sa.Column("lifecycle_updated_at", sa.DateTime(), nullable=True),
        sa.Column("lifecycle_target_completion", sa.DateTime(), nullable=True),
        sa.Column("owners", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column("links", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("changelog_token", sa.String(length=128), nullable=True),
        sa.Column("extensions", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("plan_id", name="uq_exec_plans_plan_id"),
    )
    op.create_index("ix_exec_plans_plan_id", "exec_plans", ["plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_exec_plans_plan_id", table_name="exec_plans")
    op.drop_table("exec_plans")
    op.drop_table("exec_plan_registry")
