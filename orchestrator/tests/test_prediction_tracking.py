"""Real test for app/prediction_tracking.py -- no mocking, runs
against a live Postgres (same skip-cleanly-if-unreachable pattern as
test_mattermost_webhook_concurrency.py). Creates a real Task/ToolCall,
records real outcomes against it, and asserts on the real aggregate
track-record stats, then cleans up."""
import uuid

import pytest
from sqlalchemy import delete, select

from app.db import async_session, engine
from app.models import Agent, Experiment, Org, PredictionOutcome, Task, ToolCall, ToolSource
from app.prediction_tracking import (
    InvalidOutcome,
    ToolCallNotFound,
    get_tool_track_record,
    record_prediction_outcome,
)


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    # See tests/test_methods_report.py for why this is needed -- a real,
    # confirmed-live pytest-asyncio/asyncpg-pool gotcha, not defensive
    # boilerplate.
    yield
    await engine.dispose()


async def _seeded_org_and_agent():
    async with async_session() as db:
        org = (await db.execute(select(Org).limit(1))).scalars().first()
        agent = (await db.execute(select(Agent).limit(1))).scalars().first()
        return org, agent


async def test_record_and_aggregate_real_outcomes():
    try:
        org, agent = await _seeded_org_and_agent()
    except Exception as exc:
        pytest.skip(f"Orchestrator Postgres not reachable: {exc}")
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    channel_id = f"test-track-{uuid.uuid4()}"
    tool_source_name = f"test-tool-{uuid.uuid4().hex[:8]}"
    experiment_id = task_id = tool_source_id = None
    tool_call_ids: list[uuid.UUID] = []
    outcome_ids: list[uuid.UUID] = []

    async with async_session() as db:
        experiment = Experiment(
            org_id=org.id, agent_id=agent.id, channel_id=channel_id,
            name="Prediction tracking test", folder_path="/tmp/track-test",
        )
        db.add(experiment)
        await db.flush()
        experiment_id = experiment.id

        task = Task(
            org_id=org.id, agent_id=agent.id, experiment_id=experiment_id,
            mattermost_thread_id=f"thread-{uuid.uuid4()}", requested_by_user_id="test-user",
            raw_request="Dock this compound.", status="completed",
        )
        db.add(task)
        await db.flush()
        task_id = task.id

        tool_source = ToolSource(name=tool_source_name, category="drug_discovery", mcp_server_ref="in-process:app.tools.vina_docking")
        db.add(tool_source)
        await db.flush()
        tool_source_id = tool_source.id

        for _ in range(3):
            tc = ToolCall(task_id=task_id, tool_source_id=tool_source_id, status="ok")
            db.add(tc)
            await db.flush()
            tool_call_ids.append(tc.id)
        await db.commit()

    try:
        async with async_session() as db:
            r1 = await record_prediction_outcome(db, tool_call_id=tool_call_ids[0], outcome="validated", recorded_by_user_id="researcher-1", notes="Assay confirmed binding.")
            outcome_ids.append(r1.id)
        async with async_session() as db:
            r2 = await record_prediction_outcome(db, tool_call_id=tool_call_ids[1], outcome="validated", recorded_by_user_id="researcher-1")
            outcome_ids.append(r2.id)
        async with async_session() as db:
            r3 = await record_prediction_outcome(db, tool_call_id=tool_call_ids[2], outcome="contradicted", recorded_by_user_id="researcher-2", notes="No binding observed.")
            outcome_ids.append(r3.id)

        async with async_session() as db:
            track_record = await get_tool_track_record(db, tool_source_name)

        assert track_record["found"] is True
        assert track_record["total_outcomes_recorded"] == 3
        assert track_record["validated"] == 2
        assert track_record["contradicted"] == 1
        assert track_record["validation_rate"] == round(2 / 3, 3)
    finally:
        async with async_session() as db:
            for oid in outcome_ids:
                await db.execute(delete(PredictionOutcome).where(PredictionOutcome.id == oid))
            for tcid in tool_call_ids:
                await db.execute(delete(ToolCall).where(ToolCall.id == tcid))
            await db.execute(delete(Task).where(Task.id == task_id))
            await db.execute(delete(Experiment).where(Experiment.id == experiment_id))
            await db.execute(delete(ToolSource).where(ToolSource.id == tool_source_id))
            await db.commit()


async def test_invalid_outcome_raises():
    try:
        org, agent = await _seeded_org_and_agent()
    except Exception as exc:
        pytest.skip(f"Orchestrator Postgres not reachable: {exc}")
    if org is None:
        pytest.skip("No seeded Org row -- run scripts/seed_dev_data.py first.")

    async with async_session() as db:
        with pytest.raises(InvalidOutcome):
            await record_prediction_outcome(db, tool_call_id=uuid.uuid4(), outcome="maybe", recorded_by_user_id="x")


async def test_unknown_tool_call_raises():
    try:
        org, agent = await _seeded_org_and_agent()
    except Exception as exc:
        pytest.skip(f"Orchestrator Postgres not reachable: {exc}")
    if org is None:
        pytest.skip("No seeded Org row -- run scripts/seed_dev_data.py first.")

    async with async_session() as db:
        with pytest.raises(ToolCallNotFound):
            await record_prediction_outcome(db, tool_call_id=uuid.uuid4(), outcome="validated", recorded_by_user_id="x")


async def test_unknown_tool_source_reports_not_found():
    try:
        org, agent = await _seeded_org_and_agent()
    except Exception as exc:
        pytest.skip(f"Orchestrator Postgres not reachable: {exc}")
    if org is None:
        pytest.skip("No seeded Org row -- run scripts/seed_dev_data.py first.")

    async with async_session() as db:
        result = await get_tool_track_record(db, f"nonexistent-tool-{uuid.uuid4().hex[:8]}")
    assert result["found"] is False
