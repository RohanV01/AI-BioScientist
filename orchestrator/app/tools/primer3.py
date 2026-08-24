"""A real primer3-py MCP tool (docs/10-build-plan.md Phase 5's bio.tools +
GitHub-repo triage, wave 1). PCR primer design is one of the most
common wet-lab-adjacent computational tasks and had zero coverage
before this -- every other tool source so far answers "what is known"
questions, not "how do I go do this experiment" questions.

Same shape as scikit_bio.py: real local computation (primer3-py wraps
the actual Primer3 C library, installed into the orchestrator's own
venv), no network dependency, no external record to cite -- so the
citable unit is the method itself via a bracket tag, same
methodological-citation convention as scikit-bio/cobra/vina.
"""
from typing import Any

import primer3
from claude_agent_sdk import create_sdk_mcp_server, tool


@tool(
    "design_pcr_primers",
    "Design PCR primer pairs for a DNA template sequence using Primer3, "
    "optionally targeting a specific region within it. Returns the top "
    "candidate pairs with sequences, melting temperatures, GC%, and "
    "predicted product size. Never state a primer sequence or Tm this "
    "tool didn't actually return.",
    {"sequence": str, "target_start": int, "target_length": int, "num_return": int},
)
async def design_pcr_primers(args: dict[str, Any]) -> dict[str, Any]:
    sequence = args["sequence"].strip().upper()
    if not sequence or any(c not in "ACGTN" for c in sequence):
        return {"content": [{"type": "text", "text": "sequence must be a non-empty DNA string (A/C/G/T/N only)."}]}
    if len(sequence) < 50:
        return {"content": [{"type": "text", "text": "sequence is too short for reliable primer design (need at least ~50bp)."}]}

    num_return = min(max(int(args.get("num_return") or 3), 1), 10)
    seq_args = {"SEQUENCE_ID": "query", "SEQUENCE_TEMPLATE": sequence}

    target_start = args.get("target_start")
    target_length = args.get("target_length")
    if target_start is not None and target_length is not None:
        target_start, target_length = int(target_start), int(target_length)
        if target_start < 0 or target_start + target_length > len(sequence):
            return {"content": [{"type": "text", "text": "target_start/target_length must fall within sequence."}]}
        seq_args["SEQUENCE_TARGET"] = [target_start, target_length]

    # Lower bound must never exceed the upper bound -- for a 50-74bp
    # template, a hardcoded 75 lower bound with an upper bound of
    # len(sequence) is an illegal range primer3 raises OSError on
    # ("Illegal element in PRIMER_PRODUCT_SIZE_RANGE") instead of just
    # reporting no primers found. Found via testing a 60bp input.
    product_max = min(1000, len(sequence))
    product_min = min(75, product_max)
    global_args = {
        "PRIMER_OPT_SIZE": 20, "PRIMER_MIN_SIZE": 18, "PRIMER_MAX_SIZE": 25,
        "PRIMER_OPT_TM": 60.0, "PRIMER_MIN_TM": 57.0, "PRIMER_MAX_TM": 63.0,
        "PRIMER_MIN_GC": 20.0, "PRIMER_MAX_GC": 80.0,
        "PRIMER_MAX_NS_ACCEPTED": 0, "PRIMER_NUM_RETURN": num_return,
        "PRIMER_PRODUCT_SIZE_RANGE": [[product_min, product_max]],
    }

    result = primer3.bindings.design_primers(seq_args=seq_args, global_args=global_args)
    n_found = result.get("PRIMER_PAIR_NUM_RETURNED", 0)
    if n_found == 0:
        explanation = result.get("PRIMER_LEFT_EXPLAIN", "no explanation available")
        return {"content": [{"type": "text", "text": f"No valid primer pairs found. Primer3 diagnostics: {explanation}"}]}

    # [primer3:pair_N] is the citable unit, like scikit-bio's [scikit-bio:metric].
    lines = [f"Top {n_found} PCR primer pair(s) for a {len(sequence)}bp template [primer3:pair]:"]
    for i in range(n_found):
        left_seq = result[f"PRIMER_LEFT_{i}_SEQUENCE"]
        right_seq = result[f"PRIMER_RIGHT_{i}_SEQUENCE"]
        left_tm = result[f"PRIMER_LEFT_{i}_TM"]
        right_tm = result[f"PRIMER_RIGHT_{i}_TM"]
        left_gc = result[f"PRIMER_LEFT_{i}_GC_PERCENT"]
        right_gc = result[f"PRIMER_RIGHT_{i}_GC_PERCENT"]
        product_size = result[f"PRIMER_PAIR_{i}_PRODUCT_SIZE"]
        lines.append(
            f"- Pair {i + 1}: forward {left_seq} (Tm {left_tm:.1f}C, GC {left_gc:.1f}%), "
            f"reverse {right_seq} (Tm {right_tm:.1f}C, GC {right_gc:.1f}%), "
            f"product size {product_size}bp"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_primer3_mcp_server():
    return create_sdk_mcp_server(name="primer3", tools=[design_pcr_primers])
