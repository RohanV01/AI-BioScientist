"""A real MHCflurry MCP tool (docs/12-biotools-triage-shortlist.md's
Immunoinformatics cluster) -- peptide-MHC class I binding affinity
prediction, the standard first-pass computational step in epitope
discovery (vaccine design, neoantigen prioritization in cancer
immunotherapy). Nothing else in this platform predicts immune
presentation; IEDB-style lookups would only cover already-published
epitopes, not novel candidate peptides.

Real local inference (in-process, via a pretrained pan-allele neural
network model downloaded once via `mhcflurry-downloads fetch
models_class1_pan` -- CPU-only, no GPU/CUDA required despite mhcflurry
depending on torch). Same shape as app/tools/huggingface.py's ESM2
tool: a real model producing a number, not an external database
record, so the citable unit is the model itself, tagged
[mhcflurry:allele].
"""
import asyncio
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

_predictor = None


def _get_predictor():
    global _predictor
    if _predictor is None:
        from mhcflurry import Class1AffinityPredictor

        _predictor = Class1AffinityPredictor.load()
    return _predictor


def _run_prediction(peptides: list[str], allele: str) -> dict:
    predictor = _get_predictor()
    if allele not in predictor.supported_alleles:
        raise ValueError(
            f"Allele {allele!r} is not in MHCflurry's supported list "
            f"({len(predictor.supported_alleles)} alleles). Use standard HLA "
            "nomenclature, e.g. 'HLA-A*02:01'."
        )
    df = predictor.predict_to_dataframe(peptides=peptides, allele=allele)
    return df.to_dict(orient="records")


@tool(
    "predict_mhc_binding",
    "Given one or more peptide sequences (8-15 residues, typical MHC class I "
    "epitope length) and an HLA allele (e.g. 'HLA-A*02:01'), predict binding "
    "affinity (IC50 in nM) via MHCflurry's pretrained pan-allele model. Lower "
    "IC50 means stronger predicted binding -- under ~50nM is a strong binder, "
    "under ~500nM is a weak/moderate binder by common convention. Never state "
    "an affinity value this tool didn't actually return.",
    {"peptides": list, "allele": str},
)
async def predict_mhc_binding(args: dict[str, Any]) -> dict[str, Any]:
    peptides = [p.strip().upper() for p in args["peptides"] if p.strip()]
    # HLA nomenclature is always uppercase (e.g. "HLA-A*02:01") -- without
    # normalizing case here, a real, valid allele given in a different case
    # (e.g. "hla-a*02:01") fails the supported_alleles membership check and
    # is wrongly reported as unsupported, even though peptides ARE
    # normalized the same way two lines above.
    allele = args["allele"].strip().upper()
    if not peptides:
        return {"content": [{"type": "text", "text": "peptides must contain at least one non-empty sequence."}]}
    bad = [p for p in peptides if not (8 <= len(p) <= 15) or any(c not in "ACDEFGHIKLMNPQRSTVWY" for c in p)]
    if bad:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Invalid peptide(s) {bad} -- must be 8-15 residues, standard amino acids only.",
                }
            ]
        }

    try:
        records = await asyncio.to_thread(_run_prediction, peptides, allele)
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}]}

    # [mhcflurry:allele] is the citable unit -- real local model inference,
    # same methodological-citation convention as huggingface.py's ESM2 tag.
    lines = [f"MHCflurry class I binding predictions for {allele} [mhcflurry:{allele}]:"]
    for r in records:
        ic50 = r["prediction"]
        pct = r["prediction_percentile"]
        tier = "strong binder" if ic50 < 50 else "weak/moderate binder" if ic50 < 500 else "unlikely binder"
        lines.append(f"- {r['peptide']}: IC50 {ic50:.1f}nM (percentile {pct:.2f}) -- {tier}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_mhcflurry_binding_mcp_server():
    return create_sdk_mcp_server(name="mhcflurry_binding", tools=[predict_mhc_binding])
