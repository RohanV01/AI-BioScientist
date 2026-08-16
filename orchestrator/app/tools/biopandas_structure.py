"""A real BioPandas MCP tool (docs/10-build-plan.md Phase 5's bio.tools
+ GitHub-repo triage -- BioPandas, 756+ GitHub stars, general-purpose,
actively maintained). Runs in-process against the orchestrator's own
venv, no external API call beyond fetching the structure file itself
from RCSB (BioPandas' own fetch_pdb wraps that).

Complements app/tools/pdb.py, which only returns search-result metadata
(title/resolution/method) -- this tool actually parses a structure's
atom records to report its real composition: chains, residue counts,
and bound heteroatom groups (ligands/cofactors, excluding water) --
detail no other tool in this roster can currently answer.
"""
from typing import Any

from biopandas.pdb import PandasPdb
from claude_agent_sdk import create_sdk_mcp_server, tool

# Water is present in nearly every crystal structure and isn't a
# meaningful "bound ligand" for this tool's purpose.
_EXCLUDED_HETERO = {"HOH"}


@tool(
    "get_structure_composition",
    "Given a PDB ID, fetch the real structure file and report its "
    "composition: chains, residue count per chain, and bound "
    "heteroatom/ligand groups (cofactors, inhibitors, ions -- water "
    "excluded). Complements pdb.search_structures, which only returns "
    "search metadata, not actual structural content. Never state a "
    "chain/residue/ligand this tool didn't actually find in the file.",
    {"pdb_id": str},
)
async def get_structure_composition(args: dict[str, Any]) -> dict[str, Any]:
    pdb_id = args["pdb_id"].strip().upper()
    try:
        ppdb = PandasPdb().fetch_pdb(pdb_id)
    except Exception as exc:
        return {"content": [{"type": "text", "text": f"Could not fetch/parse PDB entry {pdb_id!r}: {exc}"}]}

    atom_df = ppdb.df["ATOM"]
    hetatm_df = ppdb.df["HETATM"]
    if atom_df.empty:
        return {"content": [{"type": "text", "text": f"No ATOM records found for PDB entry {pdb_id!r}."}]}

    chains = sorted(atom_df["chain_id"].unique())
    residue_counts = atom_df.groupby("chain_id")["residue_number"].nunique().to_dict()
    ligand_groups = sorted(
        g for g in hetatm_df["residue_name"].unique() if g not in _EXCLUDED_HETERO
    ) if not hetatm_df.empty else []

    lines = [f"PDB {pdb_id} composition:"]
    lines.append(f"- Chains ({len(chains)}): {', '.join(chains)}")
    for chain in chains:
        lines.append(f"  - Chain {chain}: {residue_counts.get(chain, 0)} residues")
    lines.append(
        f"- Bound heteroatom groups (excluding water): {', '.join(ligand_groups) if ligand_groups else 'none'}"
    )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_biopandas_structure_mcp_server():
    return create_sdk_mcp_server(name="biopandas_structure", tools=[get_structure_composition])
