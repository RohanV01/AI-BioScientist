"""Real test for app/methods_report.py -- no mocking, runs against a
live Postgres (same skip-cleanly-if-unreachable pattern as
test_mattermost_webhook_concurrency.py). Creates a real Experiment ->
Task -> ToolCall/Response/GroundingLink chain, generates the real
Methods section, and asserts on its actual content, then cleans up."""
import uuid

import pytest
from sqlalchemy import delete, select

from app.db import async_session, engine
from app.methods_report import ExperimentNotFound, generate_methods_section
from app.models import Agent, Experiment, GroundingLink, Org, Response, Task, ToolCall, ToolSource


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    # app/db.py's `engine` is a module-level singleton whose asyncpg pool
    # binds to whichever event loop is running when it first connects.
    # pytest-asyncio (asyncio_mode="auto") gives each test function its
    # own event loop, so a second async DB test in the same module tries
    # to reuse connections from the first test's now-closed loop --
    # "Future ... attached to a different loop". Real, confirmed-live
    # gotcha (found running this file's own two tests together, not
    # hypothetical) -- disposing the pool after each test forces a fresh
    # connection on the next test's loop instead of reusing a stale one.
    yield
    await engine.dispose()


async def _seeded_org_and_agent():
    async with async_session() as db:
        org = (await db.execute(select(Org).limit(1))).scalars().first()
        agent = (await db.execute(select(Agent).limit(1))).scalars().first()
        return org, agent


async def test_methods_section_lists_real_tool_calls_and_citations():
    try:
        org, agent = await _seeded_org_and_agent()
    except Exception as exc:
        pytest.skip(f"Orchestrator Postgres not reachable: {exc}")
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    channel_id = f"test-methods-{uuid.uuid4()}"
    experiment_id = task_id = tool_source_id = tool_call_id = response_id = None

    async with async_session() as db:
        experiment = Experiment(
            org_id=org.id, agent_id=agent.id, channel_id=channel_id,
            name="Methods report test experiment", folder_path="/tmp/methods-test",
        )
        db.add(experiment)
        await db.flush()
        experiment_id = experiment.id

        task = Task(
            org_id=org.id, agent_id=agent.id, experiment_id=experiment_id,
            mattermost_thread_id=f"thread-{uuid.uuid4()}", requested_by_user_id="test-user",
            raw_request="What is known about EGFR?", status="completed",
        )
        db.add(task)
        await db.flush()
        task_id = task.id

        tool_source = (await db.execute(select(ToolSource).where(ToolSource.name == "pubmed"))).scalars().first()
        if tool_source is None:
            tool_source = ToolSource(name="pubmed", category="literature", mcp_server_ref="in-process:app.tools.pubmed")
            db.add(tool_source)
            await db.flush()
        tool_source_id = tool_source.id

        tool_call = ToolCall(task_id=task_id, tool_source_id=tool_source_id, status="ok")
        db.add(tool_call)
        await db.flush()
        tool_call_id = tool_call.id

        response = Response(task_id=task_id, body="EGFR is a real gene.", provenance_type="grounded")
        db.add(response)
        await db.flush()
        response_id = response.id

        db.add(GroundingLink(response_id=response_id, tool_call_id=tool_call_id, citation_label="PubMed PMID {}", record_ref="12345678"))
        await db.commit()

    try:
        async with async_session() as db:
            text = await generate_methods_section(db, experiment_id)

        assert "Methods" in text
        assert "pubmed" in text
        assert "12345678" in text
        assert "1 call" in text
    finally:
        async with async_session() as db:
            await db.execute(delete(GroundingLink).where(GroundingLink.response_id == response_id))
            await db.execute(delete(Response).where(Response.id == response_id))
            await db.execute(delete(ToolCall).where(ToolCall.id == tool_call_id))
            await db.execute(delete(Task).where(Task.id == task_id))
            await db.execute(delete(Experiment).where(Experiment.id == experiment_id))
            await db.commit()


async def test_unknown_experiment_raises():
    try:
        org, agent = await _seeded_org_and_agent()
    except Exception as exc:
        pytest.skip(f"Orchestrator Postgres not reachable: {exc}")
    if org is None:
        pytest.skip("No seeded Org row -- run scripts/seed_dev_data.py first.")

    async with async_session() as db:
        with pytest.raises(ExperimentNotFound):
            await generate_methods_section(db, uuid.uuid4())
