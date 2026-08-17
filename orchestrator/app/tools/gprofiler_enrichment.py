"""A real g:Profiler MCP tool (docs/12-biotools-triage-shortlist.md's
Transcriptomics / scRNA-seq cluster). Complements gene_set_enrichment.py
(Enrichr/gseapy): g:Profiler queries a different, independently curated
backend (GO, KEGG, Reactome, WikiPathways, TRANSFAC, mirTarBase, CORUM,
HPA, HP) via its own live REST API, and is also the standard tool for
converting gene-list identifiers across namespaces -- a genuinely
different service, not a duplicate wrapper, and useful as a
cross-check against Enrichr's results for the same gene list.
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from gprofiler import GProfiler

# organism codes g:Profiler actually recognizes -- exposing the raw
# Ensembl-style short codes (hsapiens, mmusculus, ...) rather than free
# text avoids silent empty results from a misspelled organism name.
SUPPORTED_ORGANISMS = {"hsapiens", "mmusculus", "rnorvegicus", "drerio", "dmelanogaster", "scerevisiae"}


@tool(
    "profile_gene_list",
    "Given a list of gene symbols, run functional enrichment analysis via "
    "the live g:Profiler service (GO, KEGG, Reactome, WikiPathways, and "
    "more) -- an independent enrichment backend from gseapy/Enrichr, useful "
    "as a cross-check. organism defaults to human (hsapiens); other "
    "options: " + ", ".join(sorted(SUPPORTED_ORGANISMS)) + ". Never state a "
    "term or p-value this tool didn't actually return.",
    {"genes": list, "organism": str, "max_results": int},
)
async def profile_gene_list(args: dict[str, Any]) -> dict[str, Any]:
    genes = [g.strip().upper() for g in args["genes"] if g.strip()]
    organism = (args.get("organism") or "hsapiens").strip().lower()
    max_results = min(max(int(args.get("max_results") or 10), 1), 25)

    if len(genes) < 2:
        return {"content": [{"type": "text", "text": "genes must contain at least 2 gene symbols."}]}
    if organism not in SUPPORTED_ORGANISMS:
        return {
            "content": [
                {"type": "text", "text": f"Unknown organism {organism!r} -- choose from {sorted(SUPPORTED_ORGANISMS)}."}
            ]
        }

    gp = GProfiler(return_dataframe=True)
    df = gp.profile(organism=organism, query=genes)
    if df is None or df.empty:
        return {
            "content": [
                {"type": "text", "text": f"No enriched terms found for this gene list [gprofiler:{organism}]."}
            ]
        }

    df = df.sort_values("p_value").head(max_results)

    # [gprofiler:organism] is the citable unit -- the organism/database
    # queried, same convention as gene_set_enrichment.py's [gseapy:library].
    lines = [f"g:Profiler enrichment for {len(genes)} genes ({organism}) [gprofiler:{organism}]:"]
    for _, row in df.iterrows():
        lines.append(
            f"- [{row['source']}] {row['name']} ({row['native']}): "
            f"p-value {row['p_value']:.2e}, {row['intersection_size']}/{row['term_size']} genes overlap"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_gprofiler_enrichment_mcp_server():
    return create_sdk_mcp_server(name="gprofiler_enrichment", tools=[profile_gene_list])
