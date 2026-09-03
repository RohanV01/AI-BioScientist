"""add attachment

Revision ID: d1e2f3a4b5c6
Revises: c4d5e6f7a8b9
Create Date: 2026-08-30 00:00:00.000000

Multi-stage research pipeline plan, ingestion stage: an audit trail for
every real file/URL a researcher supplies alongside a query -- none existed
before this (unlike ToolCall, nothing previously recorded what raw material
a researcher actually attached).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attachment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("experiment_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("original_ref", sa.String(), nullable=False),
        sa.Column("filename_or_title", sa.String(), nullable=True),
        sa.Column("detected_format", sa.String(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("extraction_status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiment.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attachment_experiment_id", "attachment", ["experiment_id"])


def downgrade() -> None:
    op.drop_index("ix_attachment_experiment_id", table_name="attachment")
    op.drop_table("attachment")
