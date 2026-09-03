"""Adversarial tests for app/grounding.py, per docs/19-research-publication-
readiness.md step 1's three named attacks. No mocking -- runs against a live
Postgres (same skip-cleanly-if-unreachable pattern as
test_prediction_tracking.py), creates a real Task/ToolCall with a real
response_payload, and asserts the grounding gate actually holds against
citations that don't trace back to what the tool call really returned."""
import uuid

import pytest
from sqlalchemy import delete, select

from app.db import async_session, engine
from app.grounding import Citation, GroundingViolation, create_response
from app.models import Agent, Experiment, GroundingLink, Org, Response, Task, ToolCall, ToolSource


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


class _Seeded:
    """One real Task + one real ToolCall with a real response_payload,
    created fresh per test and torn down in `finally`."""

    def __init__(self, org_id, agent_id):
        self.org_id = org_id
        self.agent_id = agent_id
        self.experiment_id = None
        self.task_id = None
        self.tool_source_id = None
        self.tool_call_id = None
        self.response_ids: list[uuid.UUID] = []

    async def __aenter__(self):
        async with async_session() as db:
            experiment = Experiment(
                org_id=self.org_id, agent_id=self.agent_id,
                channel_id=f"test-ground-{uuid.uuid4()}",
                name="Grounding adversarial test", folder_path="/tmp/ground-test",
            )
            db.add(experiment)
            await db.flush()
            self.experiment_id = experiment.id

            task = Task(
                org_id=self.org_id, agent_id=self.agent_id, experiment_id=self.experiment_id,
                mattermost_thread_id=f"thread-{uuid.uuid4()}", requested_by_user_id="test-user",
                raw_request="Look up PMID 12345678.", status="completed",
            )
            db.add(task)
            await db.flush()
            self.task_id = task.id

            tool_source = ToolSource(
                name=f"test-tool-{uuid.uuid4().hex[:8]}", category="literature", mcp_server_ref="in-process:app.tools.pubmed",
            )
            db.add(tool_source)
            await db.flush()
            self.tool_source_id = tool_source.id

            tool_call = ToolCall(
                task_id=self.task_id, tool_source_id=self.tool_source_id, status="ok",
                request_payload={"query": "EGFR resistance mutation"},
                response_payload={"results": [{"pmid": "12345678", "title": "A real paper about EGFR"}]},
            )
            db.add(tool_call)
            await db.flush()
            self.tool_call_id = tool_call.id
            await db.commit()
        return self

    async def __aexit__(self, *exc):
        async with async_session() as db:
            for rid in self.response_ids:
                await db.execute(delete(GroundingLink).where(GroundingLink.response_id == rid))
                await db.execute(delete(Response).where(Response.id == rid))
            await db.execute(delete(ToolCall).where(ToolCall.id == self.tool_call_id))
            await db.execute(delete(Task).where(Task.id == self.task_id))
            await db.execute(delete(Experiment).where(Experiment.id == self.experiment_id))
            await db.execute(delete(ToolSource).where(ToolSource.id == self.tool_source_id))
            await db.commit()


async def test_fabricated_but_plausible_record_ref_is_rejected():
    """docs/19 attack 1: a well-formed but nonexistent PMID attached to a
    real ToolCall whose payload never mentions it must not be labeled
    grounded -- this is the exact case the gate was missing before this fix."""
    org, agent = await _seeded_org_and_agent()
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    async with _Seeded(org.id, agent.id) as seeded:
        async with async_session() as db:
            with pytest.raises(GroundingViolation, match="not backed by data"):
                await create_response(
                    db, task_id=seeded.task_id, body="EGFR resistance is driven by T790M.",
                    provenance_type="grounded",
                    citations=[Citation(tool_call_id=seeded.tool_call_id, citation_label="[1]", record_ref="PMID 99999999")],
                )


async def test_genuine_citation_backed_by_real_payload_is_accepted():
    """Control: a citation whose record_ref genuinely appears in the cited
    ToolCall's response_payload must still be accepted -- the fix must not
    newly reject real citations."""
    org, agent = await _seeded_org_and_agent()
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    async with _Seeded(org.id, agent.id) as seeded:
        async with async_session() as db:
            response = await create_response(
                db, task_id=seeded.task_id, body="EGFR has an associated paper, PMID 12345678.",
                provenance_type="grounded",
                citations=[Citation(tool_call_id=seeded.tool_call_id, citation_label="[1]", record_ref="12345678")],
            )
            await db.commit()
            seeded.response_ids.append(response.id)
        assert response.provenance_type == "grounded"


async def test_empty_citation_list_cannot_be_padded_around():
    """docs/19 attack 2: provenance_type='grounded' with zero citations must
    still raise -- confirms the pre-existing check, not new behavior."""
    org, agent = await _seeded_org_and_agent()
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    async with _Seeded(org.id, agent.id) as seeded:
        async with async_session() as db:
            with pytest.raises(GroundingViolation, match="must carry at least one citation"):
                await create_response(
                    db, task_id=seeded.task_id, body="EGFR is druggable.",
                    provenance_type="grounded", citations=[],
                )


async def test_synthesis_response_cannot_carry_a_citation():
    """docs/19 attack 3: a response citing a DOI in passing prose without it
    actually backing the claim must go through provenance_type='synthesis',
    which structurally forbids attaching citations at all -- so a synthesis
    response can never smuggle in an unverified 'grounded'-style citation."""
    org, agent = await _seeded_org_and_agent()
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    async with _Seeded(org.id, agent.id) as seeded:
        async with async_session() as db:
            with pytest.raises(GroundingViolation, match="citations were provided"):
                await create_response(
                    db, task_id=seeded.task_id,
                    body="Broadly, EGFR inhibitors are a mature drug class (see e.g. PMID 12345678 in passing).",
                    provenance_type="synthesis",
                    citations=[Citation(tool_call_id=seeded.tool_call_id, citation_label="[1]", record_ref="12345678")],
                )
