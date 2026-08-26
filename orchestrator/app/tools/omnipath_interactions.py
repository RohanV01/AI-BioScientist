"""A real OmniPath MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1, Transcriptomics cluster) -- integrated signaling pathway
interactions via the `omnipath` package (a client for the free,
unauthenticated omnipathdb.org web service). Distinct from the already-
live `kegg`/`reactome`/`string` tools: OmniPath curates directed,
signed (activating/inhibiting) protein-protein signaling interactions
from 100+ underlying resources with per-interaction literature
evidence, plus ligand-receptor pairs for cell-cell communication --
neither of which KEGG's pathway diagrams, Reactome's reaction-level
detail, or STRING's undirected confidence-scored network covers.
"""
from typing import Any

import omnipath as op
from claude_agent_sdk import create_sdk_mcp_server, tool


@tool(
    "get_signaling_interactions",
    "Given a gene symbol, return real curated signaling interactions "
    "(from OmniPath's 100+ underlying resources) where that gene is "
    "either partner. Each result shows source->target gene symbols, "
    "direction, and whether it's a stimulating or inhibiting "
    "interaction, with PubMed reference counts as evidence. Distinct "
    "from kegg.py/reactome.py (pathway diagrams/reaction detail) and "
    "string_db.py (undirected confidence network) -- OmniPath gives "
    "directed, signed, literature-evidenced interactions. Never state "
    "an interaction this tool didn't actually return.",
    {"gene_symbol": str, "max_results": int},
)
async def get_signaling_interactions(args: dict[str, Any]) -> dict[str, Any]:
    gene_symbol = (args.get("gene_symbol") or "").strip().upper()
    max_results = min(int(args.get("max_results", 15)), 50)
    if not gene_symbol:
        return {"content": [{"type": "text", "text": "gene_symbol must be non-empty."}]}

    import asyncio

    def _fetch():
        return op.interactions.OmniPath.get(genesymbols=True, partners=gene_symbol, organisms="human")

    try:
        df = await asyncio.to_thread(_fetch)
    except Exception as exc:  # noqa: BLE001 -- surface real OmniPath API errors to the caller
        return {"content": [{"type": "text", "text": f"OmniPath query failed for {gene_symbol!r}: {exc}"}]}

    if df is None or df.empty:
        return {"content": [{"type": "text", "text": f"No OmniPath signaling interactions found for gene {gene_symbol!r}."}]}

    # [omnipath:gene_symbol] is the citable unit -- each interaction row
    # is backed by real curated evidence (n_references), but OmniPath
    # itself (not one paper) is the record being cited, same
    # methodological-citation convention as gseapy/gprofiler's
    # enrichment-library tags.
    lines = [
        f"OmniPath signaling interactions involving {gene_symbol} [omnipath:{gene_symbol}] "
        f"({len(df)} total, showing {min(len(df), max_results)}):"
    ]
    for _, row in df.head(max_results).iterrows():
        direction = "->" if row.get("is_directed") else "--"
        effect = "stimulates" if row.get("consensus_stimulation") else ("inhibits" if row.get("consensus_inhibition") else "modulates")
        n_refs = row.get("n_references", 0)
        lines.append(
            f"- {row['source_genesymbol']} {direction} {row['target_genesymbol']} ({effect}, {n_refs} reference(s))"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_omnipath_interactions_mcp_server():
    return create_sdk_mcp_server(name="omnipath_interactions", tools=[get_signaling_interactions])
