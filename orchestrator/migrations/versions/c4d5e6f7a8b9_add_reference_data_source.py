"""add reference_data_source

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-30 00:00:00.000000

Real freshness-checking for the reference databases baked into the
Docker image at build time (Kraken2, Kaiju, Bakta, CheckM2, CheckV,
LDSC, AMRFinderPlus, PyIR) -- built per explicit user direction after
confirming none of these auto-update on their own. Seeds one row per
source with its known-installed version as of this migration, so the
first background check has something real to compare against.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# name -> (installed_version, check_method, source_url) -- matches the
# exact versions baked into the Dockerfile (lines ~260-269) as of this
# migration's Create Date, and app/reference_data.py's REFERENCE_DATA_SOURCES
# registry.
_SEED_SOURCES = [
    ("kraken2_viral", "kraken/k2_viral_20260626.tar.gz", "s3_bucket_listing", "https://genome-idx.s3.amazonaws.com/"),
    ("kaiju_viruses", "2024/kaiju_db_viruses_2024-08-15.tgz", "s3_bucket_listing", "https://kaiju-idx.s3.eu-central-1.amazonaws.com/"),
    ("bakta_light", "14916843", "zenodo_versions_latest", "https://zenodo.org/api/records/14916843"),
    ("checkm2", "14897628", "zenodo_versions_latest", "https://zenodo.org/api/records/14897628"),
    ("ldsc_1000g_eur", "7768714", "zenodo_versions_latest", "https://zenodo.org/api/records/7768714"),
    ("checkv", "checkv-db-v1.5", "release_file", "https://portal.nersc.gov/CheckV/CURRENT_RELEASE.txt"),
    # "4.2" (from the amrfinder_binaries_v4.2.7 release used in the
    # Dockerfile) is the *binary* version, not the DB date this check
    # method actually compares against (real live inspection of the
    # built image found no local /opt/amrfinder/data/latest/version.txt
    # to read the true installed DB date from -- the two cached local
    # images available for inspection both predate this Dockerfile's
    # AMRFinderPlus addition). Seeded to the dated version live at
    # migration-authoring time (2026-08-30) as the best available
    # estimate of what a build around now would fetch -- if the actual
    # deployed image was built at a meaningfully different time,
    # correct this row's installed_version once, after which the real
    # check keeps it accurate going forward.
    ("amrfinderplus", "2026-08-10", "release_file", "https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/latest/"),
    ("pyir_imgt", "self-refreshing", "self_refreshing", "https://www.ncbi.nlm.nih.gov/igblast/"),
]


def upgrade() -> None:
    op.create_table(
        "reference_data_source",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("installed_version", sa.String(), nullable=False),
        sa.Column("latest_known_version", sa.String(), nullable=True),
        sa.Column("check_method", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("needs_update", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_check_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    table = sa.table(
        "reference_data_source",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("installed_version", sa.String()),
        sa.column("check_method", sa.String()),
        sa.column("source_url", sa.String()),
        sa.column("needs_update", sa.Boolean()),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": uuid.uuid4(),
                "name": name,
                "installed_version": version,
                "check_method": method,
                "source_url": url,
                "needs_update": False,
            }
            for name, version, method, url in _SEED_SOURCES
        ],
    )


def downgrade() -> None:
    op.drop_table("reference_data_source")
