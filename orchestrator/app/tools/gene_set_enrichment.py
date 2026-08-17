"""A real gseapy MCP tool (docs/12-biotools-triage-shortlist.md's
Transcriptomics / scRNA-seq cluster, covers both the "GSEApy" and
"Enrichr (via gseapy)" line items -- same package, same underlying
Enrichr web service). Gene-set enrichment answers "what pathways/
processes is this gene list collectively involved in" -- a real gap:
KEGG/Reactome/STRING answer per-gene pathway/interaction questions,
nothing does list-level statistical enrichment.

gseapy.enrichr() calls the real, live Enrichr REST service
(maayanlab.cloud) with the given gene list against real curated
gene-set libraries (KEGG, GO, Reactome, WikiPathways, etc.) -- not a
local/offline approximation. Real local computation happens too (the
statistical test itself), but the gene sets and background come from
a live external service, so this tool sits between the two patterns:
tagged with a bracket tag like the other wrapped-library tools since
there's no single external record ID for "an enrichment result,"
only the library queried.
"""
from typing import Any

import gseapy
from claude_agent_sdk import create_sdk_mcp_server, tool

# A deliberately small, well-known subset of Enrichr's 200+ libraries --
# covers the common "what pathway/process/disease" questions without
# overwhelming the caller with an unbounded library-name string.
ALLOWED_LIBRARIES = {
    "kegg": "KEGG_2021_Human",
    "go_biological_process": "GO_Biological_Process_2023",
    "go_molecular_function": "GO_Molecular_Function_2023",
    "reactome": "Reactome_2022",
    "wikipathways": "WikiPathways_2024_Human",
    "disease": "DisGeNET",
}


@tool(
    "enrich_gene_set",
    "Given a list of gene symbols and a library name, run gene-set "
    "enrichment analysis via gseapy against the live Enrichr service to "
    "find which pathways/processes/diseases are statistically "
    "over-represented in the list. library must be one of: "
    f"{', '.join(ALLOWED_LIBRARIES)}. Returns the top enriched terms with "
    "p-values and the overlapping genes. Never state a term or p-value "
    "this tool didn't actually return.",
    {"genes": list, "library": str, "max_results": int},
)
async def enrich_gene_set(args: dict[str, Any]) -> dict[str, Any]:
    genes = [g.strip().upper() for g in args["genes"] if g.strip()]
    library_key = (args.get("library") or "kegg").strip().lower()
    max_results = min(max(int(args.get("max_results") or 10), 1), 25)

    if len(genes) < 2:
        return {"content": [{"type": "text", "text": "genes must contain at least 2 gene symbols."}]}
    if library_key not in ALLOWED_LIBRARIES:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Unknown library {library_key!r} -- choose from {list(ALLOWED_LIBRARIES)}.",
                }
            ]
        }

    gene_set_name = ALLOWED_LIBRARIES[library_key]
    result = gseapy.enrichr(
        gene_list=genes, gene_sets=[gene_set_name], organism="human", outdir=None, no_plot=True
    )
    df = result.results
    if df is None or df.empty:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"No enriched terms found for this gene list against {gene_set_name} [gseapy:{gene_set_name}].",
                }
            ]
        }

    df = df.sort_values("Adjusted P-value").head(max_results)

    # [gseapy:library] is the citable unit -- the library queried, since
    # there's no single external record ID for a statistical enrichment
    # result the way there is for e.g. a PMID or ChEMBL compound.
    lines = [f"Gene-set enrichment for {len(genes)} genes against {gene_set_name} [gseapy:{gene_set_name}]:"]
    for _, row in df.iterrows():
        lines.append(
            f"- {row['Term']}: {row['Overlap']} genes overlap, "
            f"adj. p-value {row['Adjusted P-value']:.2e} ({row['Genes']})"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_gene_set_enrichment_mcp_server():
    return create_sdk_mcp_server(name="gene_set_enrichment", tools=[enrich_gene_set])
