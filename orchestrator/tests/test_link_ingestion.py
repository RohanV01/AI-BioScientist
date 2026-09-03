"""Real tests for app/link_ingestion.py. extract_urls is pure and tested
directly; fetch_url_text makes a real HTTP request, so it's skipped
cleanly if the network isn't reachable rather than failing the suite on
an environment that can't reach the public internet."""
import httpx
import pytest

from app.link_ingestion import extract_urls, fetch_url_text


def test_extract_urls_finds_all_and_dedupes():
    text = (
        "Check https://example.com/paper and also https://example.com/paper "
        "again (duplicate), plus https://another.example.org/data."
    )
    urls = extract_urls(text)
    assert urls == ["https://example.com/paper", "https://another.example.org/data"]


def test_extract_urls_strips_trailing_punctuation_and_markup():
    text = "See (https://example.com/x) and [https://example.com/y]."
    urls = extract_urls(text)
    assert "https://example.com/x" in urls
    assert "https://example.com/y" in urls


def test_extract_urls_empty_text_returns_empty_list():
    assert extract_urls("no links here") == []


async def test_fetch_url_text_real_fetch_or_skip():
    try:
        text = await fetch_url_text("https://example.com/")
    except Exception as exc:  # noqa: BLE001 -- network unreachable in this environment
        pytest.skip(f"Network not reachable for a real fetch test: {exc}")
    if text is None:
        pytest.skip("example.com returned no extractable content in this environment.")
    assert isinstance(text, str)
    assert len(text) > 0


async def test_fetch_url_text_unreachable_host_returns_none():
    text = await fetch_url_text("https://this-host-genuinely-does-not-exist-openbiolab-test.invalid/")
    assert text is None
