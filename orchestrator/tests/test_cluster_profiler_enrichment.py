"""Real tests for app/tools/cluster_profiler_enrichment.py -- no
mocking, runs the real Rscript wrapper around clusterProfiler
(Bioconductor, see Dockerfile). Not locally testable in this sandbox
(no R interpreter available, and Bioconductor package compilation is a
build-time Docker image step) -- validation-path tests run directly;
the happy-path run is deferred to the batch Docker build/test pass,
same as every other DB/environment-dependent tool this session."""
from app.tools.cluster_profiler_enrichment import enrich_gene_ontology_clusterprofiler


async def text_of(result):
    return result["content"][0]["text"]


async def test_too_few_genes_reports_error():
    result = await enrich_gene_ontology_clusterprofiler.handler({"genes": ["TP53", "BRCA1"], "organism": "human", "ontology": "BP"})
    text = await text_of(result)
    assert "at least 3" in text


async def test_invalid_organism_reports_error():
    genes = ["TP53", "BRCA1", "EGFR", "MYC"]
    result = await enrich_gene_ontology_clusterprofiler.handler({"genes": genes, "organism": "zebrafish", "ontology": "BP"})
    text = await text_of(result)
    assert "must be one of" in text


async def test_invalid_ontology_reports_error():
    genes = ["TP53", "BRCA1", "EGFR", "MYC"]
    result = await enrich_gene_ontology_clusterprofiler.handler({"genes": genes, "organism": "human", "ontology": "XX"})
    text = await text_of(result)
    assert "must be one of" in text
