"""add memory_fact

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-08-30 00:00:03.000000

Cross-experiment Memory layer (docs/18-platform-capability-gaps.md Pass 1
#1), inspired by (not built on) github.com/rohitg00/agentmemory's tiered-
consolidation design -- see the multi-stage research pipeline plan section
3. One row per extracted, entity-scoped finding, traced back to the real
Task/Response that produced it.

KNOWN RISK, flag before running this against a fresh environment: this
migration assumes the `vector` Postgres extension is installable in the
target database. The current docker-compose.yml pins `postgres:16-alpine`,
which does NOT ship pgvector by default -- `CREATE EXTENSION vector` will
fail there unless the image is swapped for one that bundles it (e.g.
`pgvector/pgvector:pg16-alpine`) or the extension is built into the image
separately. If that swap hasn't happened yet, this migration will fail at
the `CREATE EXTENSION` step; the rest of the schema (attachment,
task.stage, landscape_benchmark) does not depend on it and is unaffected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR

# revision identifiers, used by Alembic.
revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, Sequence[str], None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "memory_fact",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("entity_ref", sa.String(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column(
            "search_vector", TSVECTOR,
            sa.Computed("to_tsvector('english', statement)", persisted=True),
            nullable=False,
        ),
        sa.Column("source_task_id", sa.UUID(), nullable=False),
        sa.Column("source_response_id", sa.UUID(), nullable=False),
        sa.Column("experiment_id", sa.UUID(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("superseded_by_id", sa.UUID(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["source_response_id"], ["response.id"]),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiment.id"]),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["memory_fact.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_fact_entity_ref", "memory_fact", ["entity_ref"])
    op.create_index("ix_memory_fact_content_hash", "memory_fact", ["content_hash"])
    op.execute("CREATE INDEX ix_memory_fact_search_vector ON memory_fact USING GIN (search_vector)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_fact_search_vector")
    op.drop_index("ix_memory_fact_content_hash", table_name="memory_fact")
    op.drop_index("ix_memory_fact_entity_ref", table_name="memory_fact")
    op.drop_table("memory_fact")
