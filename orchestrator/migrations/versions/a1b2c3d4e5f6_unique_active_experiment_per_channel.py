"""unique active experiment per channel

Revision ID: a1b2c3d4e5f6
Revises: f177c776d2c7
Create Date: 2026-08-24 00:00:00.000000

Closes a real race condition found by concurrency testing (readiness item
#6): _resolve_or_create_experiment's read-then-write in
app/routers/mattermost_webhook.py has a TOCTOU gap -- two messages arriving
in the same brand-new channel close enough together both see "no active
experiment" and both insert one, silently splitting conversation history
across duplicate rows for the same channel. A partial unique index enforces
the single-active-experiment-per-channel invariant at the database level;
the application code now catches the resulting IntegrityError and re-reads
the winning row instead of assuming its own insert always wins.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f177c776d2c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_experiment_one_active_per_channel",
        "experiment",
        ["channel_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("ix_experiment_one_active_per_channel", table_name="experiment")
