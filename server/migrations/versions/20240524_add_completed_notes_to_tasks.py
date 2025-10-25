"""Add completed_notes column to tasks table

Revision ID: 20240524_add_completed_notes
Revises:
Create Date: 2024-05-24
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20240524_add_completed_notes"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("completed_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "completed_notes")
