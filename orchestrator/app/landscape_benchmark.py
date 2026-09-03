"""Benchmark-against-landscape stage (multi-stage research pipeline plan
section 5) -- runs after the Execute stage's Response is persisted,
classifying each claim in it against what the Landscape Scan already knew:
confirmatory, novel, or contradictory. A plain LLM comparison over two
already-produced texts, same shape as app/experiment_synthesis.py's
synthesize_conclusion -- no new tool calls, so this step itself never
raises a new grounding question.
"""
import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_backend import complete as llm_complete

logger = logging.getLogger(__name__)
from app.memory.consolidate import consolidate_facts
from app.models import LandscapeBenchmark, Response, Task

_BENCHMARK_PROMPT = """\
You are comparing a research agent's final answer against a prior survey of \
what was already known on the same topic, to classify how much of the \
answer is genuinely new information versus a restatement of what was \
already known.

For each distinct factual claim in the ANSWER below, classify it as exactly \
one of:
- "confirmatory": the claim restates or aligns with something the \
LANDSCAPE SUMMARY already established.
- "novel": the claim is not present in the LANDSCAPE SUMMARY at all -- new \
ground.
- "contradictory": the claim conflicts with something the LANDSCAPE SUMMARY \
established.

Return ONLY a JSON array (no markdown fences, no commentary) of objects, \
each shaped exactly as:
{{"claim": "the specific claim, verbatim or near-verbatim from the answer", \
"classification": "confirmatory|novel|contradictory", "rationale": "one \
sentence explaining the classification"}}

If the answer contains no meaningfully separable claims (e.g. it's a \
clarifying question or an "ungroundable" refusal), return an empty array.

LANDSCAPE SUMMARY (what was already known before this task ran):
{landscape_summary}

ANSWER (the task's final response, to classify):
{response_body}
"""


def _parse_json_array(raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    parsed = json.loads(text)
    return parsed if isinstance(parsed, list) else []


async def benchmark_against_landscape(landscape_summary: str, response_body: str) -> list[dict]:
    """Returns [{claim, classification, rationale}, ...]. Raises
    app.llm_backend.LLMBackendError / json.JSONDecodeError on failure --
    the caller decides how to report that, same contract as
    synthesize_conclusion."""
    if not landscape_summary.strip() or not response_body.strip():
        return []
    raw = await llm_complete(
        _BENCHMARK_PROMPT.format(landscape_summary=landscape_summary, response_body=response_body),
        max_tokens=2000,
    )
    return _parse_json_array(raw)


async def run_and_persist_benchmark(
    db: AsyncSession,
    *,
    landscape_task: Task,
    main_task: Task,
    response: Response,
    landscape_summary: str,
    experiment_id: uuid.UUID,
) -> list[LandscapeBenchmark]:
    """Runs the comparison, persists one LandscapeBenchmark row per claim,
    and consolidates "novel"/"contradictory" claims into the cross-
    experiment Memory layer -- a "confirmatory" claim just re-states
    something already in memory, so only genuinely new/conflicting findings
    are worth remembering."""
    classified = await benchmark_against_landscape(landscape_summary, response.body)

    rows: list[LandscapeBenchmark] = []
    novel_or_contradictory_text_parts = []
    for item in classified:
        claim = item.get("claim", "").strip()
        classification = item.get("classification", "").strip()
        rationale = item.get("rationale", "").strip()
        if not claim or classification not in {"confirmatory", "novel", "contradictory"}:
            continue

        row = LandscapeBenchmark(
            landscape_task_id=landscape_task.id, response_id=response.id,
            claim=claim, classification=classification, rationale=rationale,
        )
        db.add(row)
        rows.append(row)

        if classification == "novel":
            novel_or_contradictory_text_parts.append(claim)
        elif classification == "contradictory":
            novel_or_contradictory_text_parts.append(f"Contradicts prior finding: {claim} ({rationale})")

    if rows:
        await db.flush()

    if novel_or_contradictory_text_parts:
        # source_task/source_response point at the Execute task/response
        # that actually produced these claims -- landscape_task is only the
        # FK target on the LandscapeBenchmark rows above, not the origin of
        # the fact itself. Best-effort, same reasoning as
        # app/landscape_scan.py's own consolidate_facts call -- a memory-
        # consolidation failure must not discard the LandscapeBenchmark
        # rows already flushed above.
        try:
            await consolidate_facts(
                db, response=response, task=main_task, experiment_id=experiment_id,
                source_text="\n".join(novel_or_contradictory_text_parts),
            )
        except Exception:
            logger.exception(
                "Memory consolidation failed for benchmark on response %s; benchmark rows are unaffected.",
                response.id,
            )

    return rows
