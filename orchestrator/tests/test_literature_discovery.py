"""Real tests for app/tools/literature_discovery.py -- no mocking, hits
the real OpenAlex API and greps the real local Sci-Hub DOI index
(SCIHUB_DOI_INDEX_PATH, confirmed present in this dev environment)."""
import httpx
import pytest

from app.experiment_context import current_experiment_dir, load_manifest, update_manifest_entry
from app.tools.literature_discovery import (
    _foundational_works,
    _try_direct_oa_download,
    check_scihub_availability,
    discover_papers,
)


async def text_of(result):
    return result["content"][0]["text"]


async def test_discover_papers_happy_path():
    result = await discover_papers.handler({"query": "CRISPR Cas9 gene editing", "max_results": 3})
    text = await text_of(result)
    assert "DOI" in text


async def test_discover_papers_max_results_clamped_to_100_without_duplicates(tmp_path):
    # One live call covers the cap, the DOI dedup across the two groups, and
    # the manifest gate (every surfaced DOI recorded with its group).
    token = current_experiment_dir.set(tmp_path)
    try:
        result = await discover_papers.handler({"query": "CRISPR Cas9 genome editing", "max_results": 999})
        manifest = load_manifest()
    finally:
        current_experiment_dir.reset(token)
    text = await text_of(result)
    dois = [l.split(":")[0].removeprefix("- DOI ") for l in text.split("\n") if l.startswith("- DOI")]
    assert 50 <= len(dois) <= 100
    assert len(dois) == len(set(dois))
    assert "Foundational (most cited by the top 25 matching papers):" in text
    assert "Most relevant matches (OpenAlex relevance order):" in text
    assert {manifest[d]["discovery_group"] for d in dois} == {"foundational", "relevant_match"}


# Landmark papers the old relevance-only search (top 25) did not return for
# these keyword queries; the foundational group should.
@pytest.mark.parametrize(
    "query, landmark_doi",
    [
        ("KRAS G12C covalent inhibitor", "10.1038/nature12796"),
        ("PCSK9 loss-of-function LDL cholesterol coronary heart disease", "10.1056/nejmoa054013"),
        ("CD19 CAR T cell therapy B-cell acute lymphoblastic leukemia", "10.1056/nejmoa1709866"),
    ],
)
async def test_discover_papers_surfaces_landmark_paper(query, landmark_doi):
    result = await discover_papers.handler({"query": query})
    text = (await text_of(result)).lower()
    assert f"- doi {landmark_doi}:" in text


async def test_discover_papers_flags_retracted_work():
    # The Lancet's 2021 obesity pharmacotherapy network meta-analysis is
    # marked is_retracted in OpenAlex.
    result = await discover_papers.handler(
        {"query": "Pharmacotherapy for Overweight and Obese Adults network meta-analysis randomised controlled trials"}
    )
    line = next(l for l in (await text_of(result)).split("\n") if l.lower().startswith("- doi 10.1016/s0140-6736(21)01640-8:"))
    assert "RETRACTED" in line


async def test_foundational_works_with_no_reference_lists_is_empty_not_an_error():
    # Seeds shaped like OpenAlex search hits whose referenced_works are empty
    # or missing (common for preprints, datasets and old papers): there is
    # nothing to resolve, so no lookup call is made and no error is reported.
    seeds = [
        {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1234/a", "referenced_works": []},
        {"id": "https://openalex.org/W2", "doi": "https://doi.org/10.1234/b"},
    ]
    async with httpx.AsyncClient() as client:
        assert await _foundational_works(client, seeds, 10) == ([], None)


async def test_discover_papers_nonsense_query_returns_no_results():
    result = await discover_papers.handler({"query": "zzzznonexistentqueryimpossible98765xyz"})
    text = await text_of(result)
    assert "No OpenAlex results found" in text


async def test_check_scihub_availability_empty_list():
    result = await check_scihub_availability.handler({"dois": []})
    text = await text_of(result)
    assert "No DOIs given" in text


async def test_check_scihub_availability_open_access_doi_short_circuits():
    # A real, well-known open-access DOI (PLOS ONE article) -- should be
    # reported as open access without ever needing to grep the Sci-Hub
    # index (Gap 9's compliance boundary: OA status always checked and
    # preferred first).
    result = await check_scihub_availability.handler({"dois": ["10.1371/journal.pone.0000308"]})
    text = await text_of(result)
    assert "open access" in text.lower()
    assert "prefer this over Sci-Hub" in text


async def test_check_scihub_availability_garbage_doi_does_not_crash():
    result = await check_scihub_availability.handler({"dois": ["10.9999/not-a-real-doi-at-all-xyz"]})
    text = await text_of(result)
    assert "not open access and not found" in text.lower() or "no gnomAD" not in text.lower()


async def test_check_scihub_availability_strips_doi_url_prefix():
    # _strip_doi_prefix should handle a full https://doi.org/... URL the
    # same as a bare DOI -- confirms the OA path still resolves.
    result = await check_scihub_availability.handler(
        {"dois": ["https://doi.org/10.1371/journal.pone.0000308"]}
    )
    text = await text_of(result)
    # The DOI label itself (before the colon) must be the bare DOI, not
    # the https://doi.org/... form -- even though this paper's own OA
    # URL happens to also be a doi.org link later in the same line, which
    # a naive "URL not anywhere in the line" assertion would wrongly flag.
    doi_label = text.split(":")[0]
    assert doi_label == "- DOI 10.1371/journal.pone.0000308"


async def test_check_scihub_availability_caps_at_fifty_dois():
    dois = [f"10.1234/fake-doi-{i}" for i in range(75)]
    result = await check_scihub_availability.handler({"dois": dois})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- DOI")]
    assert len(lines) <= 50


async def test_direct_oa_download_fetches_real_pdf_bypassing_camofox(tmp_path):
    # Reliability fix: an OA paper's PDF should download via a plain
    # httpx GET, with no dependency on Camofox being configured or
    # running at all. Uses a real, stable arXiv PDF URL as the "oa_url"
    # to avoid depending on OpenAlex (whose free-tier budget this test
    # session has already exhausted -- see docs/13-test-report.md) --
    # this test only needs to prove _try_direct_oa_download's own fetch
    # +content-type-check logic, not OpenAlex's lookup.
    token = current_experiment_dir.set(tmp_path)
    try:
        doi = "10.1234/fake-test-doi-arxiv-fixture"
        update_manifest_entry(doi, oa_url="https://arxiv.org/pdf/2005.14165")
        pdf_bytes = await _try_direct_oa_download(doi)
    finally:
        current_experiment_dir.reset(token)
    assert pdf_bytes is not None
    assert pdf_bytes.startswith(b"%PDF")


async def test_direct_oa_download_returns_none_when_no_oa_url_cached(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        doi = "10.1234/fake-test-doi-no-oa-url"
        update_manifest_entry(doi, oa_url=None)
        pdf_bytes = await _try_direct_oa_download(doi)
    finally:
        current_experiment_dir.reset(token)
    assert pdf_bytes is None
