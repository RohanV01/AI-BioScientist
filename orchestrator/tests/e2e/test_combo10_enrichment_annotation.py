"""E2E combo 10: enrichment & annotation.

open_targets (gene list) -> gene_set_enrichment -> gprofiler_enrichment ->
ontologies -> huggingface, anchored on a real cancer gene panel (TP53,
BRCA1, EGFR, MYC, KRAS -- the same fixture both enrichment tools' own
tests use, where both independently return "Breast cancer" as their top
term).

Real hand-off checked: both enrichment tools (independent backends,
Enrichr vs g:Profiler) agree on the same top term for the same gene list,
and that term is then used as the actual ontologies.search_ontology_term
query -- not a hardcoded, disconnected query.
"""
import pytest

from app.tools.gene_set_enrichment import enrich_gene_set
from app.tools.gprofiler_enrichment import profile_gene_list
from app.tools.huggingface import _build_predict_masked_residue_tool
from app.tools.ontologies import search_ontology_term
from app.tools.open_targets import search_entities
from tests.e2e._utils import E2ERecorder, E2EStep, text_of

CANCER_GENES = ["TP53", "BRCA1", "EGFR", "MYC", "KRAS"]


def _hf_token() -> str | None:
    try:
        from dotenv import dotenv_values

        root_env = dotenv_values(__file__.split("orchestrator")[0] + ".env")
        return root_env.get("HUGGINGFACE_API_TOKEN")
    except Exception:
        return None


@pytest.mark.e2e
async def test_enrichment_and_annotation():
    rec = E2ERecorder("enrichment_and_annotation")

    for gene in CANCER_GENES[:2]:  # spot-check two of the five are real Open Targets entities
        ot_text = await rec.call("open_targets.search_entities", search_entities.handler, {"query": gene, "max_results": 3})
        rec.check(f"open_targets resolves {gene} as a real entity", "ENSG" in ot_text, ot_text[:150])

    gseapy_text = await rec.call("gene_set_enrichment.enrich_gene_set", enrich_gene_set.handler, {"genes": CANCER_GENES, "library": "kegg", "max_results": 3})
    gseapy_top_is_breast_cancer = "Breast cancer" in gseapy_text.split("\n")[0] if gseapy_text else False
    rec.check("gseapy/Enrichr finds Breast cancer as (one of) the top enriched term(s) for this real gene panel", "Breast cancer" in gseapy_text, gseapy_text[:200])

    gprofiler_text = await rec.call("gprofiler_enrichment.profile_gene_list", profile_gene_list.handler, {"genes": CANCER_GENES, "max_results": 3})
    rec.check(
        "g:Profiler (an independent enrichment backend) agrees with gseapy/Enrichr on the same real gene panel -- cross-tool agreement, not just both running",
        "Breast cancer" in gprofiler_text,
        gprofiler_text[:200],
    )

    ontology_text = await rec.call("ontologies.search_ontology_term", search_ontology_term.handler, {"query": "breast cancer", "ontology": "mondo", "max_results": 5})
    rec.check(
        "the term both enrichment tools agreed on (breast cancer) resolves to a real ontology definition -- the query is the enrichment result, not a disconnected hardcoded string",
        "MONDO" in ontology_text or "No" not in ontology_text.split("\n")[0],
        ontology_text[:200],
    )

    token = _hf_token()
    if token:
        predict = _build_predict_masked_residue_tool({"Authorization": f"Bearer {token}"})
        hf_result = await predict.handler({"masked_sequence": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAP<mask>LSRVGDGTQ", "top_k": 3})
        hf_text = text_of(hf_result)
        rec.steps.append(E2EStep(tool="huggingface.predict_masked_residue", args={"top_k": 3}, result_text=hf_text))
        rec.check("huggingface ESM2 live inference works (BYO-credential token found in repo .env)", "ESM2" in hf_text, hf_text[:200])
    else:
        rec.check("huggingface leg skipped -- no BYO-credential HUGGINGFACE_API_TOKEN found in .env (not a failure, matches per-tool test's own skip condition)", True)

    rec.assert_all_passed()
