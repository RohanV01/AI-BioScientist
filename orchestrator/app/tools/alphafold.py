"""A real AlphaFold DB MCP tool (docs/10-build-plan.md Phase 3,
Shortlist #8), same in-process pattern as the other tools -- EBI's
AlphaFold DB API is free and unauthenticated. Structure lookup only,
same scope boundary as app/tools/pdb.py -- no folding inference.

One tool: given a UniProt accession (from app/tools/uniprot.py's
search_protein), return the AlphaFold predicted structure's model ID,
confidence metrics, and structure file URL -- the computational
counterpart to PDB's experimentally determined structures, for targets
that don't have (or need) a crystal/cryo-EM structure.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

ALPHAFOLD_URL = "https://alphafold.ebi.ac.uk/api/prediction"


@tool(
    "get_predicted_structure",
    "Given a UniProt accession, return its AlphaFold predicted structure: "
    "model ID, per-residue confidence (pLDDT) breakdown, and a URL to "
    "the structure file. Use the AlphaFold model ID as the citable "
    "record reference -- never invent one, and never state a confidence "
    "score this tool didn't return.",
    {"uniprot_accession": str},
)
async def get_predicted_structure(args: dict[str, Any]) -> dict[str, Any]:
    accession = args["uniprot_accession"]
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{ALPHAFOLD_URL}/{accession}")
        # AlphaFold DB returns 400 (not 404) for both a malformed and an
        # unrecognized accession -- a normal "no prediction" result, not
        # a real failure worth raising on.
        if resp.status_code in (400, 404):
            return {"content": [{"type": "text", "text": f"No AlphaFold prediction found for UniProt accession {accession!r}."}]}
        resp.raise_for_status()
        predictions = resp.json()

    if not predictions:
        return {"content": [{"type": "text", "text": f"No AlphaFold prediction found for UniProt accession {accession!r}."}]}

    p = predictions[0]
    text = (
        f"AlphaFold model {p['modelEntityId']} for {p.get('gene', accession)} "
        f"({p.get('uniprotDescription', '')}, {p.get('organismScientificName', '')}): "
        f"mean confidence (pLDDT) {p.get('globalMetricValue', 'n/a')}, "
        f"{p.get('fractionPlddtVeryHigh', 0) * 100:.1f}% very high confidence, "
        f"{p.get('fractionPlddtConfident', 0) * 100:.1f}% confident, "
        f"{p.get('fractionPlddtLow', 0) * 100:.1f}% low, "
        f"{p.get('fractionPlddtVeryLow', 0) * 100:.1f}% very low. "
        f"Structure file: {p.get('cifUrl', 'n/a')}"
    )
    return {"content": [{"type": "text", "text": text}]}


def build_alphafold_mcp_server():
    return create_sdk_mcp_server(name="alphafold", tools=[get_predicted_structure])
