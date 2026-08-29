"""Real staleness reporting for the reference databases baked into the
Docker image at build time (Kraken2/Kaiju/Bakta/CheckM2/CheckV/LDSC/
AMRFinderPlus/PyIR) -- built per explicit user direction to make these
"constantly checked for releases" rather than silently frozen. Real DB
reads/writes against ReferenceDataSource via app/reference_data.py --
no external network call happens here directly, that's all in
app/reference_data.py's check functions.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import ReferenceDataSource
from app.reference_data import refresh_all_reference_data

router = APIRouter()


def _serialize(source: ReferenceDataSource) -> dict:
    return {
        "name": source.name,
        "installed_version": source.installed_version,
        "latest_known_version": source.latest_known_version,
        "needs_update": source.needs_update,
        "check_method": source.check_method,
        "source_url": source.source_url,
        "last_checked_at": source.last_checked_at.isoformat() if source.last_checked_at else None,
        "last_check_error": source.last_check_error,
    }


@router.get("/reference-data/status")
async def get_reference_data_status(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(ReferenceDataSource).order_by(ReferenceDataSource.name))
    sources = result.scalars().all()
    return {
        "sources": [_serialize(s) for s in sources],
        "stale_count": sum(1 for s in sources if s.needs_update),
    }


@router.post("/reference-data/check")
async def trigger_reference_data_check(db: AsyncSession = Depends(get_db)) -> dict:
    """Runs the real live check against every tracked source right
    now, rather than waiting for the next scheduled background pass
    (app/main.py) -- useful for verifying a source's check mechanism
    still works without waiting up to 24h."""
    sources = await refresh_all_reference_data(db)
    return {
        "sources": [_serialize(s) for s in sources],
        "stale_count": sum(1 for s in sources if s.needs_update),
    }
