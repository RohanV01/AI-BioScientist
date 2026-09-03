"""add landscape_benchmark

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-08-30 00:00:02.000000

Multi-stage research pipeline plan section 5: one row per claim in a
Response, classified against what the Landscape Scan already knew before
Execute ran (confirmatory|novel|contradictory). Deliberately not a reuse of
prediction_outcome -- that table is a human reporting real-world wet-lab
validation, a stronger tier of evidence than an LLM comparing two summaries.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "landscape_benchmark",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("landscape_task_id", sa.UUID(), nullable=False),
        sa.Column("response_id", sa.UUID(), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["landscape_task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["response_id"], ["response.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_landscape_benchmark_response_id", "landscape_benchmark", ["response_id"])


def downgrade() -> None:
    op.drop_index("ix_landscape_benchmark_response_id", table_name="landscape_benchmark")
    op.drop_table("landscape_benchmark")
