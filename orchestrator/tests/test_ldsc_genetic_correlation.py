"""Real tests for app/tools/ldsc_genetic_correlation.py -- no mocking,
runs the real ldsc.py against the baked-in EUR 1000G-Phase3/HapMap3
reference panel (see Dockerfile). The happy-path test uses 60 real
chr22 HapMap3 rsIDs (pulled from the reference panel's own
LDscore.22.l2.ldscore.gz) so they genuinely overlap the reference --
made-up rsIDs would correctly produce zero overlap."""
import random

from app.tools.ldsc_genetic_correlation import estimate_genetic_correlation

REAL_CHR22_HM3_RSIDS = [
    "rs9617528", "rs4911642", "rs7287144", "rs5748662", "rs5994034", "rs4010554", "rs4010558", "rs3954571",
    "rs11089179", "rs9604821", "rs2379965", "rs2379981", "rs4535153", "rs5747620", "rs17430900", "rs9605903",
    "rs5747940", "rs5746647", "rs16980739", "rs9605927", "rs5747968", "rs2236639", "rs5747988", "rs5746664",
    "rs5747999", "rs2070501", "rs11089263", "rs2096537", "rs16984366", "rs2154615", "rs8137637", "rs4410381",
    "rs9604967", "rs5993671", "rs5993792", "rs5992472", "rs4819849", "rs9605028", "rs1892844", "rs2529883",
    "rs17432784", "rs2845379", "rs2845380", "rs2247281", "rs2845346", "rs2845347", "rs1807512", "rs5748593",
    "rs17433377", "rs4390844", "rs2381107", "rs4819535", "rs5748648", "rs738045", "rs7284996", "rs5748651",
    "rs2385714", "rs2080203", "rs5748657", "rs2072467",
]


def _random_sumstats(seed: int) -> dict:
    rng = random.Random(seed)
    return {
        rsid: {"a1": "A", "a2": "G", "z": round(rng.gauss(0, 1), 3), "n": 50000}
        for rsid in REAL_CHR22_HM3_RSIDS
    }


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_estimates_real_genetic_correlation():
    result = await estimate_genetic_correlation.handler(
        {"trait1_sumstats": _random_sumstats(1), "trait2_sumstats": _random_sumstats(2)}
    )
    text = await text_of(result)
    assert "LDSC" in text


async def test_nonoverlapping_snps_reports_no_overlap():
    fake_sumstats = {f"rsFAKE{i}": {"a1": "A", "a2": "G", "z": 0.1, "n": 1000} for i in range(60)}
    result = await estimate_genetic_correlation.handler(
        {"trait1_sumstats": fake_sumstats, "trait2_sumstats": fake_sumstats}
    )
    text = await text_of(result)
    assert "No SNPs remain" in text or "no overlap" in text.lower()


async def test_too_few_snps_reports_error():
    small = {"rs1": {"a1": "A", "a2": "G", "z": 0.1, "n": 1000}}
    result = await estimate_genetic_correlation.handler({"trait1_sumstats": small, "trait2_sumstats": small})
    text = await text_of(result)
    assert "at least 50" in text


async def test_missing_key_reports_error():
    bad = {rsid: {"a1": "A", "a2": "G", "z": 0.1} for rsid in REAL_CHR22_HM3_RSIDS}
    result = await estimate_genetic_correlation.handler({"trait1_sumstats": bad, "trait2_sumstats": bad})
    text = await text_of(result)
    assert "a1, a2, z, and n" in text
