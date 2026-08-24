"""E2E combo 2: drug repurposing / mechanism.

chembl -> open_targets -> clinicaltrials -> dailymed -> pubmed, anchored
on imatinib (CHEMBL941) -- the same known-good fixture the per-tool tests
already use. Imatinib's real mechanism (BCR-ABL/ABL1 inhibition) is used
to link the chembl compound step to a real open_targets association
lookup, not an arbitrary/unrelated gene.
"""
import re

import pytest

from app.tools.chembl import compound_search
from app.tools.clinicaltrials import search_trials
from app.tools.dailymed import search_drug_labels
from app.tools.open_targets import get_target_disease_associations, search_entities
from app.tools.pubmed import search_articles
from tests.e2e._utils import E2ERecorder

CHEMBL_ID_RE = re.compile(r"\b(CHEMBL\d+)\b")
ENSEMBL_GENE_RE = re.compile(r"\b(ENSG\d{11})\b")


@pytest.mark.e2e
async def test_drug_repurposing_mechanism():
    rec = E2ERecorder("drug_repurposing_mechanism")

    chembl_text = await rec.call("chembl.compound_search", compound_search.handler, {"query": "imatinib", "max_results": 5})
    chembl_ids = CHEMBL_ID_RE.findall(chembl_text)
    rec.check("chembl found imatinib's ChEMBL ID (CHEMBL941)", "CHEMBL941" in chembl_ids, chembl_text[:200])

    # Imatinib's real target is ABL1 (BCR-ABL fusion kinase) -- a genuine
    # mechanism link, not an arbitrary gene chosen to make the chain work.
    ot_entities_text = await rec.call("open_targets.search_entities", search_entities.handler, {"query": "ABL1", "max_results": 5})
    abl1_ids = ENSEMBL_GENE_RE.findall(ot_entities_text)
    rec.check("open_targets resolved ABL1 (imatinib's real target) to an Ensembl gene ID", bool(abl1_ids), ot_entities_text[:200])

    if abl1_ids:
        assoc_text = await rec.call(
            "open_targets.get_target_disease_associations",
            get_target_disease_associations.handler,
            {"ensembl_id": abl1_ids[0], "max_results": 5},
        )
        rec.check("ABL1's Ensembl ID from search_entities is directly usable for a disease-association lookup", "ABL1" in assoc_text or "association score" in assoc_text, assoc_text[:200])

    trials_text = await rec.call("clinicaltrials.search_trials", search_trials.handler, {"query": "imatinib", "max_results": 5})
    rec.check("clinicaltrials found real trials for the same drug (imatinib)", "NCT ID NCT" in trials_text, trials_text[:200])

    label_text = await rec.call("dailymed.search_drug_labels", search_drug_labels.handler, {"drug_name": "imatinib", "max_results": 5})
    rec.check("dailymed found a real label for the same drug (imatinib)", "DailyMed set ID" in label_text, label_text[:200])

    lit_text = await rec.call("pubmed.search_articles", search_articles.handler, {"query": "imatinib mechanism of action", "max_results": 5})
    rec.check("pubmed found supporting literature for the same drug (imatinib)", "PMID" in lit_text, lit_text[:200])

    rec.assert_all_passed()
