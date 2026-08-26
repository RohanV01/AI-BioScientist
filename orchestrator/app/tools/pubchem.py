"""A real PubChem MCP tool (docs/17-remaining-tools-wiring-plan.md's
"newly identified gaps" section) -- PubChem's PUG-REST API is free,
unauthenticated, and covers a broader/different compound universe than
ChEMBL's bioactivity-curated scope (chembl.py), including PubChem
BioAssay screening data ChEMBL doesn't carry.

Confirmed the real API contract live before wiring (2026-08-26):
GET /rest/pug/compound/name/<name>/property/<fields>/JSON. Real quirk
found in that response: requesting the `CanonicalSMILES` property
returns a field literally named `ConnectivitySMILES` instead -- PubChem
silently renamed it server-side; not a guess, confirmed against a live
response for a known compound (aspirin) before coding around it.

One tool: resolve a compound name/synonym to its PubChem CID plus core
identifying properties (molecular formula, weight, canonical SMILES).
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PROPERTIES = "MolecularFormula,MolecularWeight,CanonicalSMILES,IUPACName"


@tool(
    "search_compound",
    "Search PubChem for a compound by name or synonym. Returns PubChem "
    "CID, molecular formula, molecular weight, canonical SMILES, and "
    "IUPAC name -- use the PubChem CID as the citable record reference, "
    "never invent one. Complements ChEMBL (chembl.py) with a broader, "
    "non-bioactivity-curated compound universe.",
    {"name": str},
)
async def search_compound(args: dict[str, Any]) -> dict[str, Any]:
    name = (args.get("name") or "").strip()
    if not name:
        return {"content": [{"type": "text", "text": "name must be non-empty."}]}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{PUBCHEM_BASE}/compound/name/{name}/property/{PROPERTIES}/JSON")
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PubChem compound found for {name!r}."}]}
        resp.raise_for_status()
        props = resp.json().get("PropertyTable", {}).get("Properties", [])

    if not props:
        return {"content": [{"type": "text", "text": f"No PubChem compound found for {name!r}."}]}

    lines = []
    for p in props:
        # PubChem returns the CanonicalSMILES property under the field
        # name ConnectivitySMILES -- confirmed live, see module docstring.
        smiles = p.get("ConnectivitySMILES") or p.get("CanonicalSMILES", "n/a")
        lines.append(
            f"- PubChem CID {p['CID']}: {p.get('IUPACName', 'no IUPAC name')}, "
            f"formula {p.get('MolecularFormula', 'n/a')}, MW {p.get('MolecularWeight', 'n/a')}, "
            f"SMILES {smiles}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_pubchem_mcp_server():
    return create_sdk_mcp_server(name="pubchem", tools=[search_compound])
