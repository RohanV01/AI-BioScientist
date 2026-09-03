"""Read path for the cross-experiment Memory layer -- hybrid retrieval over
MemoryFact rows, fused with Reciprocal Rank Fusion (RRF, k=60), same
convention github.com/rohitg00/agentmemory uses for its own three-stream
fusion. See the multi-stage research pipeline plan section 3.4.

Three streams, run independently and fused, not chained:
  - keyword: Postgres full-text (`ts_rank` against MemoryFact.search_vector)
    -- always runs, this project's BM25-equivalent.
  - vector: cosine distance against MemoryFact.embedding -- only runs when
    embeddings are actually populated. No embedding provider is wired
    anywhere in this codebase today (confirmed by inspection before writing
    this module -- app/llm_backend.py has no embedding call), so this
    stream is a no-op for now; app/memory/consolidate.py leaves `embedding`
    null, and this degrades to keyword+entity retrieval only, never a hard
    failure. Wiring a real embedding provider is future work, not a corner
    cut here -- the retrieval code already accounts for it.
  - entity: exact `entity_ref IN (...)` match -- the cheapest and most
    precise stream, and this project's stand-in for agentmemory's "graph"
    stream, since it's not similarity-based at all.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MemoryFact

_RRF_K = 60
_STREAM_LIMIT = 20  # candidates pulled per stream before fusion


async def _keyword_stream(db: AsyncSession, query_text: str, limit: int) -> list[uuid.UUID]:
    tsquery = func.plainto_tsquery("english", query_text)
    result = await db.execute(
        select(MemoryFact.id)
        .where(MemoryFact.superseded_by_id.is_(None), MemoryFact.search_vector.op("@@")(tsquery))
        .order_by(func.ts_rank(MemoryFact.search_vector, tsquery).desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _vector_stream(db: AsyncSession, query_embedding: list[float] | None, limit: int) -> list[uuid.UUID]:
    if query_embedding is None:
        return []
    result = await db.execute(
        select(MemoryFact.id)
        .where(MemoryFact.superseded_by_id.is_(None), MemoryFact.embedding.is_not(None))
        .order_by(MemoryFact.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    return list(result.scalars().all())


async def _entity_stream(db: AsyncSession, entity_refs: list[str], limit: int) -> list[uuid.UUID]:
    if not entity_refs:
        return []
    result = await db.execute(
        select(MemoryFact.id)
        .where(MemoryFact.superseded_by_id.is_(None), MemoryFact.entity_ref.in_(entity_refs))
        .order_by(MemoryFact.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def _reciprocal_rank_fusion(streams: list[list[uuid.UUID]]) -> list[uuid.UUID]:
    """score(id) = sum(1 / (k + rank)) across every stream it appears in,
    rank 0-indexed within each stream. Streams that didn't run (empty list)
    simply contribute nothing -- fusion works over however many streams
    actually produced results."""
    scores: dict[uuid.UUID, float] = {}
    for stream in streams:
        for rank, fact_id in enumerate(stream):
            scores[fact_id] = scores.get(fact_id, 0.0) + 1.0 / (_RRF_K + rank)
    return sorted(scores, key=lambda fid: scores[fid], reverse=True)


async def recall_prior_findings(
    db: AsyncSession,
    *,
    query_text: str,
    entity_refs: list[str] | None = None,
    query_embedding: list[float] | None = None,
    limit: int = 10,
) -> list[MemoryFact]:
    """Hybrid recall over everything this platform has previously found and
    consolidated into memory, across every experiment -- not scoped to the
    calling experiment, since the whole point is "has anyone here looked at
    this before," anywhere. Excludes any fact with `superseded_by_id` set,
    so only the latest version of a given finding is ever recalled."""
    keyword_ids = await _keyword_stream(db, query_text, _STREAM_LIMIT)
    vector_ids = await _vector_stream(db, query_embedding, _STREAM_LIMIT)
    entity_ids = await _entity_stream(db, entity_refs or [], _STREAM_LIMIT)

    fused_ids = _reciprocal_rank_fusion([keyword_ids, vector_ids, entity_ids])[:limit]
    if not fused_ids:
        return []

    result = await db.execute(select(MemoryFact).where(MemoryFact.id.in_(fused_ids)))
    by_id = {f.id: f for f in result.scalars().all()}
    # Preserve fusion order -- the `IN` query above doesn't guarantee it.
    return [by_id[fid] for fid in fused_ids if fid in by_id]
