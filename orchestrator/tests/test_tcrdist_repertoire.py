"""Real tests for app/tools/tcrdist_repertoire.py -- no mocking, runs the
real tcrdist3 local computation."""
from app.tools.tcrdist_repertoire import compute_tcr_distances

TCRS = [
    {"cdr3_b_aa": "CASSQETQYF", "v_b_gene": "TRBV5-1*01", "j_b_gene": "TRBJ2-5*01"},
    {"cdr3_b_aa": "CASSLGQAYEQYF", "v_b_gene": "TRBV27*01", "j_b_gene": "TRBJ2-7*01"},
    {"cdr3_b_aa": "CASSPWTGGTDTQYF", "v_b_gene": "TRBV19*01", "j_b_gene": "TRBJ2-3*01"},
]


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_distance_matrix():
    result = await compute_tcr_distances.handler({"tcrs": TCRS})
    text = await text_of(result)
    assert "TCRdist" in text
    assert "3 TCRs" in text


async def test_too_few_tcrs_reports_error():
    result = await compute_tcr_distances.handler({"tcrs": [TCRS[0]]})
    text = await text_of(result)
    assert "at least 2" in text


async def test_missing_field_reports_error():
    bad = [{"cdr3_b_aa": "CASSQETQYF", "v_b_gene": "TRBV5-1*01"}, TCRS[1]]
    result = await compute_tcr_distances.handler({"tcrs": bad})
    text = await text_of(result)
    assert "missing required field" in text


async def test_invalid_gene_name_reports_error_not_crash():
    bad = [
        {"cdr3_b_aa": "CASSQETQYF", "v_b_gene": "NOTAGENE*01", "j_b_gene": "TRBJ2-5*01"},
        TCRS[1],
    ]
    result = await compute_tcr_distances.handler({"tcrs": bad})
    text = await text_of(result)
    assert "TCRdist pairwise" in text or "failed" in text
