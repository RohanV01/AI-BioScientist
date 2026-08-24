"""Real concurrency regression test against a live Postgres for
_resolve_or_create_experiment (app/routers/mattermost_webhook.py).

Found by load/concurrency testing (readiness item #6): the original
read-then-write had a TOCTOU gap -- concurrent messages to a brand-new
Mattermost channel could each see "no active experiment" and each insert
one, silently splitting conversation history across duplicate rows.
migrations/versions/a1b2c3d4e5f6 adds a partial unique index
(one active experiment per channel_id); the application code catches the
resulting IntegrityError and re-reads the winning row. This test proves the
fix under genuine concurrent DB access, not just by reading the code.

Requires the orchestrator's own Postgres reachable at ORCHESTRATOR_DB_URL
(defaults to the docker-compose port-mapped localhost:5432) with at least
one seeded Org/Agent row -- skips cleanly if either isn't available, same
as this suite's other live-dependency tests.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, select

from app.db import async_session
from app.models import Agent, Experiment, Org
from app.routers.mattermost_webhook import _resolve_or_create_experiment


async def _seeded_org_and_agent():
    async with async_session() as db:
        org = (await db.execute(select(Org).limit(1))).scalars().first()
        agent = (await db.execute(select(Agent).limit(1))).scalars().first()
        return org, agent


async def test_concurrent_first_messages_create_exactly_one_experiment():
    try:
        org, agent = await _seeded_org_and_agent()
    except Exception as exc:
        pytest.skip(f"Orchestrator Postgres not reachable: {exc}")
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    channel_id = f"test-race-{uuid.uuid4()}"

    async def resolve():
        async with async_session() as db:
            experiment = await _resolve_or_create_experiment(db, org.id, agent.id, channel_id)
            await db.commit()
            return experiment.id

    try:
        ids = await asyncio.gather(*(resolve() for _ in range(10)))
        assert len(set(ids)) == 1, "all 10 concurrent calls must resolve to the same experiment"

        async with async_session() as db:
            result = await db.execute(select(Experiment).where(Experiment.channel_id == channel_id))
            rows = result.scalars().all()
        assert len(rows) == 1, f"expected exactly 1 experiment row for the channel, found {len(rows)}"
    finally:
        async with async_session() as db:
            await db.execute(delete(Experiment).where(Experiment.channel_id == channel_id))
            await db.commit()
