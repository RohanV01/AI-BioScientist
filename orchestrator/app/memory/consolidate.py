"""Write path for the cross-experiment Memory layer -- extracts discrete,
entity-scoped facts out of an already-produced Response and upserts them as
MemoryFact rows. See the multi-stage research pipeline plan section 3.3.

Two call sites share this one function:
  1. Right after the Landscape Scan's own Response is created -- its
     synthesis already states "what's established" as prose; this extracts
     that into discrete facts.
  2. After app/landscape_benchmark.py classifies the Execute stage's
     claims -- only the "novel"/"contradictory" ones are worth remembering
     (a "confirmatory" claim just re-states something already in memory),
     passed in via `source_text` rather than the whole Response body.

Deliberately a plain LLM call over already-produced text, same shape as
app/experiment_synthesis.py's synthesize_conclusion -- no new tool calls, so
no new grounding question is raised by this step itself; the *fact rows*
this produces are what future grounding traces back to when recalled via
app/memory/retrieve.py.
"""
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_backend import LLMBackendError
from app.llm_backend import complete as llm_complete
from app.models import MemoryFact, Response, Task

_EXTRACTION_PROMPT = """\
Extract discrete, entity-scoped facts from the research text below, for a \
long-term scientific memory index. Each fact must be:
- Atomic: one single claim, not a compound sentence joining several.
- Entity-scoped: tagged with the specific gene/compound/disease/pathway/etc. \
it's about, formatted as "<kind>:<identifier>" (e.g. "gene:EGFR", \
"compound:CHEMBL553", "disease:MONDO_0018997") -- use whatever specific \
identifier or name the text itself provides, don't invent one.
- Self-contained: understandable without the surrounding text.

Skip vague, hedged, or purely procedural statements ("we looked into X") --
only extract genuine factual claims. If the text contains no genuine
extractable facts, return an empty list.

Return ONLY a JSON array (no markdown fences, no commentary) of objects, \
each shaped exactly as:
{{"entity_ref": "<kind>:<identifier>", "statement": "the fact, one sentence"}}

Text:
{text}
"""


def _parse_json_array(raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    parsed = json.loads(text)
    return parsed if isinstance(parsed, list) else []


def _content_hash(entity_ref: str, statement: str) -> str:
    return hashlib.sha256(f"{entity_ref}|{statement}".encode()).hexdigest()


async def consolidate_facts(
    db: AsyncSession, *, response: Response, task: Task, experiment_id, source_text: str | None = None,
) -> list[MemoryFact]:
    """Extracts facts from `source_text` (default: `response.body`) and
    upserts them as MemoryFact rows, deduped on content_hash -- an
    exact-duplicate fact is a no-op, not a new row. Raises
    app.llm_backend.LLMBackendError / json.JSONDecodeError on extraction
    failure; the caller decides how to report that (consistent with
    synthesize_conclusion's contract). Returns only the newly-inserted
    rows, not pre-existing duplicates that were skipped."""
    text = source_text if source_text is not None else response.body
    if not text or not text.strip():
        return []

    raw = await llm_complete(_EXTRACTION_PROMPT.format(text=text), max_tokens=2000)
    extracted = _parse_json_array(raw)

    inserted: list[MemoryFact] = []
    for item in extracted:
        entity_ref = item.get("entity_ref", "").strip()
        statement = item.get("statement", "").strip()
        if not entity_ref or not statement:
            continue

        content_hash = _content_hash(entity_ref, statement)
        existing = await db.execute(select(MemoryFact.id).where(MemoryFact.content_hash == content_hash))
        if existing.scalar_one_or_none() is not None:
            continue  # exact duplicate -- no-op, not a new row

        fact = MemoryFact(
            entity_ref=entity_ref, statement=statement,
            source_task_id=task.id, source_response_id=response.id, experiment_id=experiment_id,
            embedding=None,  # no embedding provider wired in this codebase yet -- see retrieve.py's module docstring
            content_hash=content_hash,
        )
        db.add(fact)
        inserted.append(fact)

    if inserted:
        await db.flush()
    return inserted
