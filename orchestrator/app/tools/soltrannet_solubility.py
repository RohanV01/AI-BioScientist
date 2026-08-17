"""A real SolTranNet MCP tool (docs/12-biotools-triage-shortlist.md's
Cheminformatics cluster). SolTranNet predicts aqueous solubility (log S)
directly from a SMILES string via a pretrained molecule-transformer
model -- a real gap: ChEMBL gives bioactivity, Vina gives binding
affinity, but nothing here answers "will this compound actually
dissolve," a basic ADMET screen that filters out promising-looking
binders that are pharmaceutically unusable.

Real local model inference (in-process, CPU, no external API for the
prediction itself), same shape as huggingface.py/mhcflurry_binding.py
-- the citable unit is the model, tagged [soltrannet:smiles].
"""
import asyncio
import hashlib
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


def _run_prediction(smiles: list[str]) -> list[tuple]:
    import soltrannet

    return list(soltrannet.predict(smiles))


@tool(
    "predict_aqueous_solubility",
    "Given one or more SMILES strings, predict aqueous solubility (log S, "
    "log mol/L) via SolTranNet's pretrained molecule-transformer model. "
    "Lower (more negative) log S means less soluble -- below -4 is "
    "generally considered poorly soluble for oral drug development. "
    "Never state a solubility value this tool didn't actually return.",
    {"smiles": list},
)
async def predict_aqueous_solubility(args: dict[str, Any]) -> dict[str, Any]:
    smiles = [s.strip() for s in args["smiles"] if s.strip()]
    if not smiles:
        return {"content": [{"type": "text", "text": "smiles must contain at least one non-empty SMILES string."}]}

    results = await asyncio.to_thread(_run_prediction, smiles)

    lines = ["SolTranNet aqueous solubility predictions:"]
    for pred, smi, warning in results:
        # [soltrannet:smiles] is the citable unit -- real local model
        # inference, same methodological-citation convention as
        # huggingface.py/mhcflurry_binding.py. Tag keyed by a short hash
        # of the SMILES since raw SMILES can contain regex-hostile
        # characters ([, ], =, #) that would break bracket-tag matching.
        tag = hashlib.sha1(smi.encode()).hexdigest()[:8]
        note = f" ({warning})" if warning else ""
        lines.append(f"- {smi}: log S = {pred:.2f} [soltrannet:{tag}]{note}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_soltrannet_solubility_mcp_server():
    return create_sdk_mcp_server(name="soltrannet_solubility", tools=[predict_aqueous_solubility])
