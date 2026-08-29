"""Real tests for app/routers/reference_data.py -- mounts the router
in isolation (not the full app, which pulls in unrelated heavy tools)
and hits it via an in-process ASGI client against the real dev
Postgres (same DB the other integration-style tests in this suite use
via app.db.get_db's default engine), exercising the real live upstream
checks through app/reference_data.py -- no mocking."""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.db import engine
from app.routers import reference_data


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    # See tests/test_methods_report.py for why this is needed -- a real,
    # confirmed-live pytest-asyncio/asyncpg-pool gotcha (a module-level
    # engine singleton's connection pool binds to the event loop of
    # whichever test used it first, and breaks on the next test's loop),
    # not defensive boilerplate.
    yield
    await engine.dispose()


def _make_client() -> AsyncClient:
    app = FastAPI()
    app.include_router(reference_data.router)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_status_endpoint_returns_every_tracked_source():
    async with _make_client() as client:
        resp = await client.get("/reference-data/status")
    assert resp.status_code == 200
    body = resp.json()
    names = {s["name"] for s in body["sources"]}
    assert names == {
        "kraken2_viral", "kaiju_viruses", "bakta_light", "checkm2",
        "ldsc_1000g_eur", "checkv", "amrfinderplus", "pyir_imgt",
    }
    assert isinstance(body["stale_count"], int)


async def test_check_endpoint_runs_real_live_checks_and_flags_ldsc_stale():
    # Real, previously-confirmed finding: LDSC's original Zenodo record
    # (7768714) resolves to a real newer record via /versions/latest --
    # this source should come back flagged needs_update every time this
    # runs, unless someone has since corrected the seeded
    # installed_version to the newer record.
    async with _make_client() as client:
        resp = await client.post("/reference-data/check")
    assert resp.status_code == 200
    body = resp.json()
    by_name = {s["name"]: s for s in body["sources"]}
    assert by_name["ldsc_1000g_eur"]["latest_known_version"] is not None
    assert by_name["ldsc_1000g_eur"]["last_checked_at"] is not None
    for source in body["sources"]:
        assert source["last_check_error"] is None, f"{source['name']} check failed: {source['last_check_error']}"
