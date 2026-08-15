"""
Platform-wide map-reduce-then-synthesize primitive.
Strategy (tree vs single-pass) is chosen from provider.capabilities automatically.
Every chunk is persisted to llm_chunks for crash-safe resume.
"""
from __future__ import annotations
import logging
from typing import Callable, List, Type, Optional
from pydantic import BaseModel

from .provider import LLMProvider

log = logging.getLogger(__name__)


def map_reduce(
    *,
    run_id: str,
    task: str,
    items: List,
    map_prompt_fn: Callable,
    map_schema: Type[BaseModel],
    reduce_prompt_fn: Callable,
    reduce_schema: Type[BaseModel],
    provider: LLMProvider,
    db,                           # Supabase client (passed in to avoid circular import)
    reduce_fanin: int = 8,
    temperature: float = 0.1,
) -> dict:
    """
    Run the full map-reduce pipeline over `items`.
    Returns the validated dict from the final reduce output.
    """
    chunk_size = provider.chunk_size()
    chunks = _chunk(items, chunk_size)
    total = len(chunks)

    # ── MAP ─────────────────────────────────────────────────────────────────
    chunk_outputs: List[dict] = []
    for idx, chunk in enumerate(chunks):
        existing = _load_chunk(db, run_id, task, idx)
        if existing is not None:
            log.info("  [map-reduce] %s chunk %d/%d — resumed from DB", task, idx, total)
            chunk_outputs.append(existing)
            continue

        prompt = map_prompt_fn(chunk)
        result = provider.complete(prompt, schema=map_schema, temperature=temperature)

        if result.parsed is None:
            log.warning("  [map-reduce] %s chunk %d — parse failed, skipping", task, idx)
            continue

        _save_chunk(db, run_id, task, idx, total, result.parsed)
        chunk_outputs.append(result.parsed)
        log.info("  [map-reduce] %s chunk %d/%d — done", task, idx, total)

    # ── REDUCE ───────────────────────────────────────────────────────────────
    mode = provider.reduce_mode()
    if mode == "single_pass":
        final = _reduce_single_pass(
            chunk_outputs, reduce_prompt_fn, reduce_schema, provider, temperature
        )
    else:
        final = _reduce_tree(
            chunk_outputs, reduce_prompt_fn, reduce_schema, provider, temperature, reduce_fanin
        )

    return final


def _reduce_single_pass(
    partials: List[dict],
    prompt_fn: Callable,
    schema: Type[BaseModel],
    provider: LLMProvider,
    temperature: float,
) -> dict:
    prompt = prompt_fn(partials)
    result = provider.complete(prompt, schema=schema, temperature=temperature)
    return result.parsed or {}


def _reduce_tree(
    partials: List[dict],
    prompt_fn: Callable,
    schema: Type[BaseModel],
    provider: LLMProvider,
    temperature: float,
    fanin: int,
) -> dict:
    current = partials
    round_num = 0
    while len(current) > 1:
        next_level: List[dict] = []
        for group in _chunk(current, fanin):
            prompt = prompt_fn(group)
            result = provider.complete(prompt, schema=schema, temperature=temperature)
            if result.parsed:
                next_level.append(result.parsed)
        current = next_level
        round_num += 1
        log.info("  [map-reduce] tree round %d → %d nodes", round_num, len(current))

    return current[0] if current else {}


def _chunk(lst: List, size: int) -> List[List]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def _load_chunk(db, run_id: str, task: str, idx: int) -> Optional[dict]:
    try:
        resp = (
            db.table("llm_chunks")
            .select("output_json")
            .eq("run_id", run_id)
            .eq("task", task)
            .eq("chunk_index", idx)
            .eq("status", "done")
            .single()
            .execute()
        )
        return resp.data["output_json"] if resp.data else None
    except Exception:
        return None


def _save_chunk(db, run_id: str, task: str, idx: int, total: int, output: dict) -> None:
    try:
        db.table("llm_chunks").upsert(
            {
                "run_id": run_id,
                "task": task,
                "chunk_index": idx,
                "total_chunks": total,
                "output_json": output,
                "status": "done",
            },
            on_conflict="run_id,task,chunk_index",
        ).execute()
    except Exception as exc:
        log.warning("  [map-reduce] failed to persist chunk %d: %s", idx, exc)
