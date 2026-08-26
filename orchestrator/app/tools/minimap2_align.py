"""A real Minimap2 MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1, Sequence analysis cluster) -- versatile pairwise sequence
alignment via `mappy` (minimap2's official Python bindings, a real
compiled extension, not a subprocess wrapper). Complements the already-
live `msa` (MAFFT, multiple-sequence alignment of closely-related
sequences) with a different real gap: mapping one query sequence against
a longer reference (long reads, cDNA-to-genome, or one sequence against
another genome-scale sequence) -- a job MAFFT is not designed for and
BLAST+ (not yet wired, Phase 2) is the traditional but much heavier
alternative to.
"""
from typing import Any

import mappy as mp
from claude_agent_sdk import create_sdk_mcp_server, tool

VALID_PRESETS = {"map-ont", "map-pb", "map-hifi", "sr", "asm5", "asm10", "splice"}


@tool(
    "align_to_reference",
    "Align a query sequence against a reference sequence via minimap2 "
    "(real compiled aligner, not a heuristic). preset controls the "
    "alignment mode: 'sr' for short accurate reads, 'map-ont'/'map-pb'/"
    "'map-hifi' for long reads, 'asm5'/'asm10' for genome-to-genome "
    "assembly comparison, 'splice' for cDNA-to-genome (default 'map-ont'). "
    "Returns each mapping hit's reference/query coordinates, strand, "
    "mapping quality, and CIGAR string. Never state an alignment "
    "coordinate this tool didn't actually compute.",
    {"reference": str, "query": str, "preset": str},
)
async def align_to_reference(args: dict[str, Any]) -> dict[str, Any]:
    reference = (args.get("reference") or "").strip().upper()
    query = (args.get("query") or "").strip().upper()
    preset = args.get("preset") or "map-ont"

    if not reference or not query:
        return {"content": [{"type": "text", "text": "Both reference and query must be non-empty sequences."}]}
    if preset not in VALID_PRESETS:
        return {"content": [{"type": "text", "text": f"preset must be one of {sorted(VALID_PRESETS)}, got {preset!r}."}]}

    try:
        aligner = mp.Aligner(seq=reference, preset=preset)
    except Exception as exc:  # noqa: BLE001 -- surface real minimap2 index-build errors to the caller
        return {"content": [{"type": "text", "text": f"Failed to build minimap2 index for the reference: {exc}"}]}
    if not aligner:
        return {"content": [{"type": "text", "text": "Failed to build minimap2 index for the reference (empty or invalid sequence)."}]}

    hits = list(aligner.map(query))
    if not hits:
        return {"content": [{"type": "text", "text": f"No alignment found (preset {preset!r}) -- query does not map to this reference."}]}

    # [minimap2:preset] is the citable unit -- real local computation
    # against caller-supplied sequences, same methodological-citation
    # convention as mafft/piqtree.
    lines = [f"Minimap2 alignment ({preset}) [minimap2:{preset}] -- {len(hits)} hit(s):"]
    for h in hits:
        lines.append(
            f"- query {h.q_st}-{h.q_en} ({'+' if h.strand == 1 else '-'} strand) -> "
            f"reference {h.r_st}-{h.r_en}, mapq {h.mapq}, {h.mlen}/{h.blen} matched bases, cigar {h.cigar_str}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_minimap2_mcp_server():
    return create_sdk_mcp_server(name="minimap2_align", tools=[align_to_reference])
