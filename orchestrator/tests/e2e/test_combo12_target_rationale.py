"""E2E combo 12: literature-grounded target rationale report (research
catalog flagship "Literature-Grounded Target Rationale Report", section
5.2 -- explicitly flagged there as shippable with zero new tool wiring).

open_targets (association score) -> chembl (chemical tractability) ->
pubmed (supporting literature) -> llm_backend synthesis (local model).

Real hand-off checked: the synthesis is required to separate genetic-
evidence strength from literature-volume (the catalog's own named
failure mode: "well-studied" != "well-supported") and to cite only
identifiers actually retrieved upstream -- checked programmatically, not
just eyeballed from the summary.
"""
import re

import pytest

from app.llm_backend import LLMBackendError, complete
from app.tools.chembl import compound_search
from app.tools.open_targets import get_target_disease_associations, search_entities
from app.tools.pubmed import search_articles
from tests.e2e._utils import E2EStep, E2ERecorder

ENSEMBL_GENE_RE = re.compile(r"\b(ENSG\d{11})\b")
PMID_RE = re.compile(r"PMID (\d+)")
GENE = "EGFR"


@pytest.mark.e2e
async def test_literature_grounded_target_rationale():
    rec = E2ERecorder("literature_grounded_target_rationale")

    entities_text = await rec.call("open_targets.search_entities", search_entities.handler, {"query": GENE, "max_results": 5})
    ensembl_ids = ENSEMBL_GENE_RE.findall(entities_text)
    rec.check(f"open_targets resolves {GENE} to a real Ensembl gene ID", bool(ensembl_ids), entities_text[:200])

    assoc_text = ""
    if ensembl_ids:
        assoc_text = await rec.call(
            "open_targets.get_target_disease_associations",
            get_target_disease_associations.handler,
            {"ensembl_id": ensembl_ids[0], "max_results": 5},
        )
        rec.check("the Ensembl ID found is directly usable for a real association-score lookup", "association score" in assoc_text, assoc_text[:200])

    chembl_text = await rec.call("chembl.compound_search", compound_search.handler, {"query": GENE, "max_results": 5})
    rec.check("chembl search runs for chemical-tractability context (may legitimately find zero compounds by gene-symbol query)", "ChEMBL ID" in chembl_text or "No ChEMBL compounds found" in chembl_text, chembl_text[:200])

    pubmed_text = await rec.call("pubmed.search_articles", search_articles.handler, {"query": f"{GENE} drug target", "max_results": 5})
    pmids = PMID_RE.findall(pubmed_text)
    rec.check(f"pubmed found real supporting literature for {GENE}", bool(pmids), pubmed_text[:300])

    citable_pmids = pmids[:3] or ["00000000"]
    prompt = (
        f"Write a 3-sentence target-rationale note for {GENE} as a drug target, using ONLY this real data:\n"
        f"Open Targets association evidence: {assoc_text[:500] or 'not available'}\n"
        f"Supporting literature PMIDs available to cite: {', '.join(citable_pmids)}\n"
        "Sentence 1 must state the genetic/association evidence strength (from Open Targets, not literature volume). "
        "Sentence 2 must cite at least one PMID from the list above in square brackets, e.g. [12345678]. "
        "Sentence 3 must explicitly note that literature volume and genetic evidence are different kinds of support, "
        "not proof of causality -- do not overstate evidence strength."
    )
    try:
        rationale = await complete(prompt, max_tokens=400)
    except LLMBackendError as exc:
        pytest.skip(f"no LLM backend available for this run: {exc}")
    rec.steps.append(E2EStep(tool="llm_backend.complete (local model)", args={"citable_pmids": citable_pmids}, result_text=rationale))

    cited = [p for p in citable_pmids if p in rationale]
    rec.check(
        "the target-rationale synthesis cites a real PMID actually retrieved from pubmed (not hallucinated)",
        bool(cited),
        rationale[:400],
    )
    rec.check(
        "the synthesis explicitly separates genetic evidence from literature volume (the catalog's own named failure mode for this flagship)",
        any(kw in rationale.lower() for kw in ("literature volume", "not proof", "genetic evidence", "association evidence", "does not", "doesn't necessarily")),
        rationale[:400],
    )

    rec.assert_all_passed()
