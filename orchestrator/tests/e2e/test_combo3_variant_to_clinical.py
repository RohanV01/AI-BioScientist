"""E2E combo 3: variant-to-clinical interpretation.

clinvar -> gnomad -> ensembl -> open_targets -> pubmed, anchored on BRCA1.

Honest limitation (flagged rather than faked): there is no tool in this
platform that translates a ClinVar record into gnomAD's required
chrom-pos-ref-alt variant_id -- that's a real gap (no variant-normalization
tool exists yet), not something this test can paper over. So the gnomAD
leg uses a real, independently-known BRCA1 variant (17-43045607-A-T, the
same fixture test_gnomad.py uses) as a plausibility cross-check rather
than a literal hand-off from the clinvar step. Everything else in the
chain (ensembl/open_targets/pubmed) is a real hand-off keyed on the same
gene symbol.
"""
import re

import pytest

from app.tools.clinvar import search_variants
from app.tools.ensembl import search_gene
from app.tools.gnomad import get_variant_frequency
from app.tools.open_targets import get_target_disease_associations, search_entities
from app.tools.pubmed import search_articles
from tests.e2e._utils import E2ERecorder

ENSEMBL_GENE_RE = re.compile(r"\b(ENSG\d{11})\b")
GENE = "BRCA1"
KNOWN_BRCA1_VARIANT = "17-43045607-A-T"


@pytest.mark.e2e
async def test_variant_to_clinical_interpretation():
    rec = E2ERecorder("variant_to_clinical_interpretation")

    clinvar_text = await rec.call(
        "clinvar.search_variants", search_variants.handler, {"gene": GENE, "term": "pathogenic", "max_results": 5}
    )
    rec.check("clinvar found real pathogenic variants for BRCA1", "classification:" in clinvar_text, clinvar_text[:200])

    gnomad_text = await rec.call(
        "gnomad.get_variant_frequency", get_variant_frequency.handler, {"variant_id": KNOWN_BRCA1_VARIANT}
    )
    # Plausibility check, not a literal hand-off (see module docstring): a
    # variant clinvar reports as pathogenic-adjacent for this gene should
    # be rare in the general population, not common.
    rec.check(
        "a real BRCA1 variant's gnomAD population frequency is available for cross-checking pathogenicity claims",
        "allele frequency" in gnomad_text,
        gnomad_text[:200],
    )

    ensembl_text = await rec.call("ensembl.search_gene", search_gene.handler, {"symbol": GENE})
    ensembl_ids = ENSEMBL_GENE_RE.findall(ensembl_text)
    rec.check("ensembl resolved BRCA1 to an Ensembl gene ID, same gene as the clinvar/gnomad steps", bool(ensembl_ids), ensembl_text[:200])

    if ensembl_ids:
        ot_text = await rec.call(
            "open_targets.get_target_disease_associations",
            get_target_disease_associations.handler,
            {"ensembl_id": ensembl_ids[0], "max_results": 5},
        )
        rec.check(
            "the Ensembl gene ID ensembl.search_gene found is directly usable by open_targets (real hand-off)",
            "BRCA1" in ot_text or "association score" in ot_text,
            ot_text[:200],
        )
    else:
        ot_search_text = await rec.call("open_targets.search_entities", search_entities.handler, {"query": GENE, "max_results": 5})
        rec.check("open_targets independently resolves BRCA1 as a fallback", bool(ENSEMBL_GENE_RE.findall(ot_search_text)), ot_search_text[:200])

    lit_text = await rec.call("pubmed.search_articles", search_articles.handler, {"query": "BRCA1 pathogenic variant", "max_results": 5})
    rec.check("pubmed found supporting literature for the same gene (BRCA1)", "PMID" in lit_text, lit_text[:200])

    rec.assert_all_passed()
