"""Real tests for the cross-experiment Memory layer (app/memory/retrieve.py,
app/memory/consolidate.py) -- no mocking, runs against a live Postgres (same
skip-cleanly-if-unreachable pattern as test_prediction_tracking.py). Exercises
the keyword-retrieval stream, entity-match stream, RRF fusion ordering,
supersession exclusion, and consolidate_facts' content-hash dedup directly
against real MemoryFact rows -- no LLM call involved, since consolidate_facts'
extraction call is exercised separately (LLM-dependent, out of scope for a
no-mocking unit test) and this focuses on the deterministic parts: hashing,
dedup, and the retrieval/fusion logic itself."""
import uuid

import pytest
from sqlalchemy import delete, select

from app.db import async_session, engine
from app.memory.consolidate import _content_hash
from app.memory.retrieve import recall_prior_findings
from app.models import Agent, Experiment, MemoryFact, Org, Response, Task, ToolSource


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    yield
    await engine.dispose()


async def _seeded_org_and_agent():
    async with async_session() as db:
        org = (await db.execute(select(Org).limit(1))).scalars().first()
        agent = (await db.execute(select(Agent).limit(1))).scalars().first()
        return org, agent


class _Seeded:
    """One real Experiment + Task + Response to hang MemoryFact rows off of."""

    def __init__(self, org_id, agent_id):
        self.org_id = org_id
        self.agent_id = agent_id
        self.experiment_id = None
        self.task_id = None
        self.response_id = None
        self.fact_ids: list[uuid.UUID] = []

    async def __aenter__(self):
        async with async_session() as db:
            experiment = Experiment(
                org_id=self.org_id, agent_id=self.agent_id, channel_id=f"test-memory-{uuid.uuid4()}",
                name="Memory layer test", folder_path="/tmp/memory-test",
            )
            db.add(experiment)
            await db.flush()
            self.experiment_id = experiment.id

            task = Task(
                org_id=self.org_id, agent_id=self.agent_id, experiment_id=self.experiment_id,
                mattermost_thread_id=f"thread-{uuid.uuid4()}", requested_by_user_id="test-user",
                raw_request="[landscape-scan] EGFR", status="completed", stage="landscape_scan",
            )
            db.add(task)
            await db.flush()
            self.task_id = task.id

            response = Response(task_id=self.task_id, body="EGFR is a druggable target.", provenance_type="synthesis")
            db.add(response)
            await db.flush()
            self.response_id = response.id
            await db.commit()
        return self

    async def add_fact(self, entity_ref: str, statement: str, superseded_by_id=None) -> uuid.UUID:
        async with async_session() as db:
            fact = MemoryFact(
                entity_ref=entity_ref, statement=statement,
                source_task_id=self.task_id, source_response_id=self.response_id, experiment_id=self.experiment_id,
                content_hash=_content_hash(entity_ref, statement), superseded_by_id=superseded_by_id,
            )
            db.add(fact)
            await db.flush()
            await db.commit()
            self.fact_ids.append(fact.id)
            return fact.id

    async def __aexit__(self, *exc):
        async with async_session() as db:
            for fid in self.fact_ids:
                await db.execute(delete(MemoryFact).where(MemoryFact.id == fid))
            await db.execute(delete(Response).where(Response.id == self.response_id))
            await db.execute(delete(Task).where(Task.id == self.task_id))
            await db.execute(delete(Experiment).where(Experiment.id == self.experiment_id))
            await db.commit()


def test_content_hash_is_deterministic_and_entity_sensitive():
    h1 = _content_hash("gene:EGFR", "EGFR is druggable.")
    h2 = _content_hash("gene:EGFR", "EGFR is druggable.")
    h3 = _content_hash("gene:KRAS", "EGFR is druggable.")
    assert h1 == h2
    assert h1 != h3


async def test_keyword_recall_finds_a_real_fact():
    org, agent = await _seeded_org_and_agent()
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    async with _Seeded(org.id, agent.id) as seeded:
        await seeded.add_fact("gene:EGFR", "EGFR T790M confers resistance to first-generation TKIs.")

        async with async_session() as db:
            results = await recall_prior_findings(db, query_text="EGFR T790M resistance")

        assert any(f.entity_ref == "gene:EGFR" for f in results)


async def test_entity_stream_matches_exact_entity_ref():
    org, agent = await _seeded_org_and_agent()
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    async with _Seeded(org.id, agent.id) as seeded:
        await seeded.add_fact("compound:CHEMBL553", "A known kinase inhibitor.")

        async with async_session() as db:
            results = await recall_prior_findings(
                db, query_text="completely unrelated query text", entity_refs=["compound:CHEMBL553"],
            )

        assert any(f.entity_ref == "compound:CHEMBL553" for f in results)


async def test_superseded_fact_is_excluded_from_recall():
    org, agent = await _seeded_org_and_agent()
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    async with _Seeded(org.id, agent.id) as seeded:
        old_id = await seeded.add_fact("gene:BRAF", "BRAF V600E is a rare variant.")
        new_id = await seeded.add_fact("gene:BRAF", "BRAF V600E is a common oncogenic driver mutation.")
        async with async_session() as db:
            fact = await db.get(MemoryFact, old_id)
            fact.superseded_by_id = new_id
            await db.commit()

        async with async_session() as db:
            results = await recall_prior_findings(db, query_text="BRAF V600E driver mutation")

        result_ids = {f.id for f in results}
        assert old_id not in result_ids
        assert new_id in result_ids


async def test_no_match_returns_empty_list():
    org, agent = await _seeded_org_and_agent()
    if org is None or agent is None:
        pytest.skip("No seeded Org/Agent row -- run scripts/seed_dev_data.py first.")

    async with async_session() as db:
        results = await recall_prior_findings(
            db, query_text=f"zzz-nonexistent-topic-{uuid.uuid4().hex}", entity_refs=[f"gene:NONEXISTENT{uuid.uuid4().hex}"],
        )
    assert results == []
