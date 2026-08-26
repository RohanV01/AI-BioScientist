"""A real cBioPortal MCP tool (docs/17-remaining-tools-wiring-plan.md's
Other cluster) -- cBioPortal's own free, unauthenticated REST API via
the `pybioportal` client, real cancer-genomics mutation data across
thousands of public studies (TCGA and others). A different question
than anything else in the roster: ClinVar/gnomAD answer "is this
variant pathogenic/how common is it in the general population",
cBioPortal answers "how often is this gene actually mutated in real
patient tumor cohorts, and what mutations show up."

One tool: given a gene symbol and a cBioPortal study ID (e.g.
'acc_tcga' for the TCGA Adrenocortical Carcinoma cohort), resolve the
gene to its Entrez ID and fetch real somatic mutations from that
study's default mutation profile/sample list -- both of which follow
cBioPortal's own `<study_id>_mutations` / `<study_id>_all` naming
convention, confirmed live against a real study before wiring.
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from pybioportal import genes as pb_genes
from pybioportal import mutations as pb_mutations


@tool(
    "get_gene_mutations_in_study",
    "Given a gene symbol (e.g. 'TP53') and a cBioPortal study ID (e.g. "
    "'acc_tcga' -- the TCGA Adrenocortical Carcinoma cohort; study IDs "
    "follow cBioPortal's own naming, typically '<cancer>_tcga'), fetch "
    "real somatic mutations reported for that gene across the study's "
    "patient samples. Returns each mutation's sample ID, protein change, "
    "mutation type, and variant allele. Never state a mutation this tool "
    "didn't actually return.",
    {"gene_symbol": str, "study_id": str, "max_results": int},
)
async def get_gene_mutations_in_study(args: dict[str, Any]) -> dict[str, Any]:
    gene_symbol = (args.get("gene_symbol") or "").strip().upper()
    study_id = (args.get("study_id") or "").strip().lower()
    max_results = min(int(args.get("max_results", 20)), 100)
    if not gene_symbol or not study_id:
        return {"content": [{"type": "text", "text": "Both gene_symbol and study_id must be non-empty."}]}

    try:
        gene_df = pb_genes.get_gene(gene_symbol)
    except Exception:  # noqa: BLE001 -- pybioportal raises a raw Exception on a 404 (unknown gene symbol), confirmed live
        gene_df = None
    if gene_df is None or gene_df.empty:
        return {"content": [{"type": "text", "text": f"No cBioPortal gene record found for symbol {gene_symbol!r}."}]}
    entrez_id = str(gene_df.iloc[0]["entrezGeneId"])

    mol_profile_id = f"{study_id}_mutations"
    sample_list_id = f"{study_id}_all"
    try:
        muts_df = pb_mutations.get_muts_in_mol_prof_by_sample_list_id(
            molecular_profile_id=mol_profile_id,
            sample_list_id=sample_list_id,
            entrez_gene_id=entrez_id,
            pageSize=max_results,
        )
    except Exception as exc:  # noqa: BLE001 -- surface real cBioPortal API errors (e.g. unknown study_id) to the caller
        return {
            "content": [
                {"type": "text", "text": f"cBioPortal query failed for study {study_id!r} (tried profile {mol_profile_id!r}, sample list {sample_list_id!r}): {exc}"}
            ]
        }

    if muts_df is None or muts_df.empty:
        return {"content": [{"type": "text", "text": f"No mutations found for {gene_symbol} (Entrez {entrez_id}) in cBioPortal study {study_id!r}."}]}

    lines = [f"cBioPortal mutations: {gene_symbol} (Entrez {entrez_id}) in study {study_id!r} -- {len(muts_df)} record(s):"]
    for _, row in muts_df.iterrows():
        lines.append(
            f"- sample {row.get('sampleId', 'n/a')}: {row.get('proteinChange', 'n/a')} "
            f"({row.get('mutationType', 'n/a')}, {row.get('referenceAllele', '?')}>{row.get('variantAllele', '?')})"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_cbioportal_mutations_mcp_server():
    return create_sdk_mcp_server(name="cbioportal_mutations", tools=[get_gene_mutations_in_study])
