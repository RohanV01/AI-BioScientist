"""add prediction_outcome

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-08-29 00:00:00.000000

docs/18-platform-capability-gaps.md Pass 1 #2: closes the "no feedback
loop between prediction and reality" gap -- one row per real-world
outcome report against a specific ToolCall (a docking affinity, a
solubility prediction, ...), so the platform can eventually answer "how
often has this tool's prediction actually held up" instead of only ever
reporting a fresh, uncalibrated number.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prediction_outcome",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tool_call_id", sa.UUID(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tool_call_id"], ["tool_call.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prediction_outcome_tool_call_id", "prediction_outcome", ["tool_call_id"])


def downgrade() -> None:
    op.drop_index("ix_prediction_outcome_tool_call_id", table_name="prediction_outcome")
    op.drop_table("prediction_outcome")
