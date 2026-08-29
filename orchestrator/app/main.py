import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import async_session
from app.reference_data import refresh_all_reference_data
from app.routers import mattermost_webhook, prediction_outcomes, reference_data, reports

logger = logging.getLogger(__name__)

# How often the reference-data freshness check (app/reference_data.py)
# re-queries every tracked source's real upstream endpoint -- daily is
# plenty given none of these sources release more than a few times a
# year; POST /reference-data/check exists for an on-demand check
# without waiting for this.
REFERENCE_DATA_CHECK_INTERVAL_SECONDS = 24 * 60 * 60


async def _reference_data_check_loop() -> None:
    while True:
        try:
            async with async_session() as db:
                await refresh_all_reference_data(db)
        except Exception:  # noqa: BLE001 -- a failed check cycle must not kill the loop
            logger.exception("Reference data freshness check cycle failed")
        await asyncio.sleep(REFERENCE_DATA_CHECK_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_reference_data_check_loop())
    yield
    task.cancel()


app = FastAPI(
    title="OpenBioLab Orchestrator",
    description="Routes Mattermost messages to Claude Code/Codex agents; enforces grounding on every response.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(mattermost_webhook.router)
app.include_router(reports.router)
app.include_router(prediction_outcomes.router)
app.include_router(reference_data.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
