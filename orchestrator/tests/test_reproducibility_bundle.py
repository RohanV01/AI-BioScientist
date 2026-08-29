"""Real test for app/reproducibility_bundle.py -- no mocking, runs
against a live Postgres (same skip-cleanly-if-unreachable pattern as
test_mattermost_webhook_concurrency.py). Creates a real Experiment ->
Task -> ToolCall/Response/GroundingLink chain, generates the real
bundle, and asserts on its actual content, then cleans up."""
import uuid

import pytest
from sqlalchemy import delete, select

from app.db import async_session, engine
from app.models import Agent, Experiment, GroundingLink, Org, Response, Task, ToolCall, ToolSource
from app.reproducibility_bundle import ResponseNotFound, generate_reproducibility_bundle


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


async def test_bundle_contains_real_tool_calls_and_citations():
    try:
        org, agent = await _seeded_org_and_agent()
    except Exception as exc:
        pytest.skip(f"Orchestrator Postgres not reachable: {exc}")
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    channel_id = f"test-bundle-{uuid.uuid4()}"
    experiment_id = task_id = tool_source_id = tool_call_id = response_id = None

    async with async_session() as db:
        experiment = Experiment(
            org_id=org.id, agent_id=agent.id, channel_id=channel_id,
            name="Bundle test experiment", folder_path="/tmp/bundle-test",
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

        tool_call = ToolCall(
            task_id=task_id, tool_source_id=tool_source_id, status="ok",
            request_payload={"query": "EGFR"}, response_payload={"pmids": ["12345678"]},
        )
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
            bundle = await generate_reproducibility_bundle(db, response_id)

        assert bundle["response_id"] == str(response_id)
        assert bundle["provenance_type"] == "grounded"
        assert bundle["total_tool_calls"] == 1
        assert bundle["total_citations"] == 1
        assert bundle["tool_calls"][0]["tool_source"] == "pubmed"
        assert bundle["tool_calls"][0]["request_payload"] == {"query": "EGFR"}
        assert bundle["tool_calls"][0]["cited_by_this_response"][0]["record_ref"] == "12345678"
        assert bundle["task"]["raw_request"] == "What is known about EGFR?"
    finally:
        async with async_session() as db:
            await db.execute(delete(GroundingLink).where(GroundingLink.response_id == response_id))
            await db.execute(delete(Response).where(Response.id == response_id))
            await db.execute(delete(ToolCall).where(ToolCall.id == tool_call_id))
            await db.execute(delete(Task).where(Task.id == task_id))
            await db.execute(delete(Experiment).where(Experiment.id == experiment_id))
            await db.commit()


async def test_unknown_response_raises():
    try:
        org, _ = await _seeded_org_and_agent()
    except Exception as exc:
        pytest.skip(f"Orchestrator Postgres not reachable: {exc}")
    if org is None:
        pytest.skip("No seeded Org row -- run scripts/seed_dev_data.py first.")

    async with async_session() as db:
        with pytest.raises(ResponseNotFound):
            await generate_reproducibility_bundle(db, uuid.uuid4())
