"""A real AbLang MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
1, Immunoinformatics cluster) -- antibody-specific protein language
model, wired for its `restore` mode: given a heavy- or light-chain
sequence with unknown/uncertain positions marked '*', predict the most
likely residue at each masked position. Real local model inference
(ablang's pretrained heavy/light checkpoints), not a lookup.

AbLang's model download was observed to stall in this environment on an
earlier attempt this session (near-zero bytes/sec, unlike HunFlair's
steady-but-slow progress) -- confirmed live on a retry (2026-08-26) that
this was transient: both heavy and light checkpoints downloaded and
loaded in under 70s, and a real masked-sequence restore call correctly
recovered the original residues at every masked position. Loads the
requested chain's model lazily on first call, not at import time, to
keep container startup fast (same pattern as hunflair_ner.py).
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

_MODELS: dict[str, Any] = {}


def _get_model(chain: str):
    if chain not in _MODELS:
        import ablang

        model = ablang.pretrained(chain)
        model.freeze()
        _MODELS[chain] = model
    return _MODELS[chain]


@tool(
    "restore_antibody_sequence",
    "Given an antibody heavy- or light-chain amino acid sequence with "
    "unknown/uncertain positions marked as '*' (e.g. from a low-quality "
    "sequencing read), use AbLang (antibody-specific protein language "
    "model) to predict the most likely residue at each masked position. "
    "chain must be 'heavy' or 'light'. Real local model inference, not a "
    "lookup or a guess. Never state a restored residue this tool didn't "
    "actually predict.",
    {"sequence": str, "chain": str},
)
async def restore_antibody_sequence(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    chain = (args.get("chain") or "").strip().lower()
    if chain not in ("heavy", "light"):
        return {"content": [{"type": "text", "text": "chain must be 'heavy' or 'light'."}]}
    if len(sequence) < 10:
        return {"content": [{"type": "text", "text": "sequence must be at least 10 residues long."}]}
    if "*" not in sequence:
        return {"content": [{"type": "text", "text": "sequence must contain at least one '*' masked position to restore."}]}
    if not set(sequence) <= set("ACDEFGHIKLMNPQRSTVWY*"):
        return {"content": [{"type": "text", "text": "sequence must contain only standard amino acid letters and '*' for masked positions."}]}

    import asyncio

    def _run():
        model = _get_model(chain)
        return model([sequence], mode="restore")[0]

    try:
        restored = await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001 -- surface real ablang/model errors to the caller
        return {"content": [{"type": "text", "text": f"AbLang restore failed: {exc}"}]}

    diffs = [f"position {i + 1}: {orig} -> {new}" for i, (orig, new) in enumerate(zip(sequence, restored)) if orig == "*"]
    lines = [
        f"AbLang [ablang:{chain}] restored {len(diffs)} masked position(s):",
        f"Restored sequence: {restored}",
    ]
    lines.extend(f"- {d}" for d in diffs)
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_ablang_restore_mcp_server():
    return create_sdk_mcp_server(name="ablang_restore", tools=[restore_antibody_sequence])
