"""A real epitopepredict MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1, Immunoinformatics cluster). Real local computation via the
`epitopepredict` package's TEPITOPEpan implementation (pure Python, no
external binary/database download) -- complements the already-live
`mhcflurry_binding` tool, which only covers MHC class I. This tool covers
MHC class II (HLA-DRB1 alleles), the T-helper-epitope side MHCflurry has
no coverage of at all.

Confirmed the package's real API before wiring it (2026-08-26): `predict`
takes an explicit `peptides` list, not a whole protein sequence, so this
tool does the sliding-window fragmentation itself (matching
`create_fragments`'s own overlap=1 default) and passes the resulting
9-mers straight to `TEpitopePredictor.predict`.
"""
from typing import Any

import epitopepredict as ep
from claude_agent_sdk import create_sdk_mcp_server, tool

PREDICTOR = ep.get_predictor("tepitope")
PEPTIDE_LENGTH = 9


@tool(
    "predict_mhc_ii_epitopes",
    "Given a protein sequence and an MHC class II allele (e.g. "
    "'HLA-DRB1*0101'), predict candidate T-helper (CD4+) epitopes via "
    "TEPITOPEpan (epitopepredict package) -- pure computation, no external "
    "API. Complements the mhcflurry_binding tool, which only covers MHC "
    "class I. Returns the top-scoring 9-mer peptides with their binding "
    "score and rank. Never state a score this tool didn't actually "
    "compute.",
    {"sequence": str, "allele": str, "top_n": int},
)
async def predict_mhc_ii_epitopes(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    allele = args.get("allele") or "HLA-DRB1*0101"
    top_n = min(int(args.get("top_n", 10)), 30)

    if len(sequence) < PEPTIDE_LENGTH:
        return {"content": [{"type": "text", "text": f"sequence must be at least {PEPTIDE_LENGTH} residues long."}]}
    if allele not in PREDICTOR.get_alleles():
        return {
            "content": [
                {"type": "text", "text": f"Unknown allele {allele!r} -- must be a valid HLA-DRB1 allele name, e.g. 'HLA-DRB1*0101'."}
            ]
        }

    peptides = [sequence[i:i + PEPTIDE_LENGTH] for i in range(len(sequence) - PEPTIDE_LENGTH + 1)]
    result = PREDICTOR.predict(peptides=peptides, allele=allele, name="query")
    if result is None or result.empty:
        return {"content": [{"type": "text", "text": "TEPITOPEpan produced no scored peptides for this input."}]}

    top = result.sort_values("score", ascending=False).head(top_n)
    lines = [f"MHC-II (TEPITOPEpan, {allele}) top {len(top)} candidate epitopes [epitopepredict:tepitope]:"]
    for _, row in top.iterrows():
        lines.append(f"- {row['peptide']} (position {int(row['pos'])}, score {row['score']:.3f}, rank {int(row['rank'])})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_epitopepredict_mcp_server():
    return create_sdk_mcp_server(name="epitopepredict", tools=[predict_mhc_ii_epitopes])
