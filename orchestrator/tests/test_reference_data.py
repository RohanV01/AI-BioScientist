"""Real tests for app/reference_data.py -- no mocking, hits the actual
live upstream endpoints each check_method uses (Zenodo's
/versions/latest API, S3 bucket listing, the source's own release-file
endpoint), same "verify against the real thing" convention as
test_literature_discovery.py. Each mechanism was independently
confirmed live during development before being wired in; these tests
re-confirm the parsing logic against whatever the live response looks
like today, without asserting an exact version value that will
naturally change over time as new releases ship."""
import re

from app.models import ReferenceDataSource
from app.reference_data import CheckResult, check_latest_version


def _source(name: str, installed_version: str, check_method: str, source_url: str) -> ReferenceDataSource:
    return ReferenceDataSource(
        name=name, installed_version=installed_version, check_method=check_method, source_url=source_url,
    )


async def test_zenodo_versions_latest_resolves_bakta_record():
    source = _source("bakta_light", "14916843", "zenodo_versions_latest", "https://zenodo.org/api/records/14916843")
    result = await check_latest_version(source)
    assert result.error is None
    assert result.latest_version is not None
    assert result.latest_version.isdigit()


async def test_zenodo_versions_latest_finds_newer_ldsc_record():
    # Known real finding from live investigation: querying the original
    # LDSC record 7768714 resolves to a real, different, newer record
    # (10515792, "S-LDSC reference files") -- confirms this mechanism
    # actually surfaces a real update, not just echoing back the same ID.
    source = _source("ldsc_1000g_eur", "7768714", "zenodo_versions_latest", "https://zenodo.org/api/records/7768714")
    result = await check_latest_version(source)
    assert result.error is None
    assert result.latest_version != "7768714"


async def test_s3_bucket_listing_finds_kraken2_viral_releases():
    source = _source(
        "kraken2_viral", "kraken/k2_viral_20200101.tar.gz", "s3_bucket_listing", "https://genome-idx.s3.amazonaws.com/"
    )
    result = await check_latest_version(source)
    assert result.error is None
    assert "k2_viral" in result.latest_version
    assert re.search(r"\d{8}", result.latest_version)


async def test_s3_bucket_listing_finds_kaiju_viruses_releases():
    source = _source(
        "kaiju_viruses", "kaiju_db_viruses_2020-01-01", "s3_bucket_listing",
        "https://kaiju-idx.s3.eu-central-1.amazonaws.com/",
    )
    result = await check_latest_version(source)
    assert result.error is None
    assert "kaiju_db_viruses" in result.latest_version


async def test_release_file_reads_checkv_current_release():
    source = _source(
        "checkv", "checkv-db-v0.1", "release_file", "https://portal.nersc.gov/CheckV/CURRENT_RELEASE.txt"
    )
    result = await check_latest_version(source)
    assert result.error is None
    assert result.latest_version.startswith("checkv-db-v")


async def test_release_file_reads_amrfinderplus_latest_dir():
    source = _source(
        "amrfinderplus", "0.0", "release_file",
        "https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/latest/",
    )
    result = await check_latest_version(source)
    assert result.error is None
    assert re.match(r"\d{4}-\d{2}-\d{2}", result.latest_version)


async def test_self_refreshing_source_reports_installed_version_as_current():
    source = _source("pyir_imgt", "self-refreshing", "self_refreshing", "https://www.ncbi.nlm.nih.gov/igblast/")
    result = await check_latest_version(source)
    assert result == CheckResult(latest_version="self-refreshing", error=None)


async def test_unknown_check_method_reports_error_not_a_fabricated_version():
    source = _source("mystery_source", "1.0", "not_a_real_method", "https://example.com")
    result = await check_latest_version(source)
    assert result.latest_version is None
    assert "Unknown check_method" in result.error


async def test_unreachable_url_reports_error_not_a_fabricated_version():
    source = _source(
        "kraken2_viral", "k2_viral_20200101", "s3_bucket_listing", "https://this-host-does-not-exist.invalid/"
    )
    result = await check_latest_version(source)
    assert result.latest_version is None
    assert result.error is not None
