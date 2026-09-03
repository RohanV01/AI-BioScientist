"""add task.stage

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-30 00:00:01.000000

Multi-stage research pipeline plan section 6: distinguishes a Landscape
Scan's own child Task from the main Plan/Execute/Synthesize Task without
string-matching raw_request's "[landscape-scan] " prefix. Nullable for
backfill safety, same precedent as Task.experiment_id -- existing rows stay
NULL, read as "main" by any code that cares.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task", sa.Column("stage", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("task", "stage")
