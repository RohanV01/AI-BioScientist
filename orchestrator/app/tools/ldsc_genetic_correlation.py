"""A real LDSC (LD Score Regression) MCP tool
(docs/17-remaining-tools-wiring-plan.md Phase 2, Population genetics
cluster) -- subprocess-wrapped `ldsc.py` (real PyPI package `ldsc`,
confirmed live: its wheel installs the real script + `ldscore` library,
not a namesquat, despite the project's own README only documenting a
conda-from-source install). Real genetic-correlation estimation
(Bulik-Sullivan et al. 2015) between two GWAS traits' summary
statistics, using LD Score regression -- distinct from any per-variant
lookup elsewhere on this platform (gnomAD/ClinVar/Ensembl): this
estimates a genome-wide relationship between two *traits*, not a fact
about one variant.

Ships its own EUR 1000G-Phase3 LD-score reference panel (baked into the
image at build time -- see Dockerfile) since ldsc.py --rg requires one;
the caller's SNPs must overlap that reference panel's HapMap3 SNP set
(real rsIDs) or no genetic correlation can be computed -- surfaced as a
real "no SNPs remain" error rather than fabricated.
"""
import asyncio
import gzip
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

LDSC_REF_LDSCORE_PREFIX = "/opt/ldsc_ref/LDscore/LDscore."
LDSC_REF_WEIGHTS_PREFIX = "/opt/ldsc_ref/1000G_Phase3_weights_hm3_no_MHC/weights.hm3_noMHC."

# Confirmed against a real ldsc.py --rg log's output format.
RG_MATCH = re.compile(r"^\s*(\S+\.sumstats\.gz)\s+(\S+\.sumstats\.gz)\s+([\-\d.]+|nan)\s+([\-\d.]+|nan)\s+([\-\d.]+|nan)\s+([\-\d.]+|nan)\s+([\-\d.]+|nan)")


def _validate_sumstats(sumstats: dict, label: str) -> str | None:
    if not isinstance(sumstats, dict) or len(sumstats) < 50:
        return f"{label} must be a dict of at least 50 {{rsid: {{a1, a2, z, n}}}} entries -- LD Score regression needs many SNPs to be meaningful."
    for rsid, info in list(sumstats.items())[:5] + list(sumstats.items())[-5:]:
        if not isinstance(info, dict) or not all(k in info for k in ("a1", "a2", "z", "n")):
            return f"{label} entry '{rsid}' must have a1, a2, z, and n keys."
    return None


def _write_sumstats(sumstats: dict, path: Path) -> None:
    with gzip.open(path, "wt") as fh:
        fh.write("SNP\tN\tZ\tA1\tA2\n")
        for rsid, info in sumstats.items():
            fh.write(f"{rsid}\t{info['n']}\t{info['z']}\t{info['a1']}\t{info['a2']}\n")


def _run_ldsc_rg(sumstats1: Path, sumstats2: Path, out_stem: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            "ldsc.py", "--rg", f"{sumstats1},{sumstats2}",
            "--ref-ld-chr", LDSC_REF_LDSCORE_PREFIX,
            "--w-ld-chr", LDSC_REF_WEIGHTS_PREFIX,
            "--out", str(out_stem),
        ],
        capture_output=True, text=True, timeout=300,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "estimate_genetic_correlation",
    "Given two GWAS summary-statistics sets (each a dict of {rsid: "
    "{\"a1\": str, \"a2\": str, \"z\": float, \"n\": int}}, at least 50 "
    "real dbSNP rsIDs each), estimate the real genetic correlation "
    "between the two traits via LD Score regression (LDSC). Only SNPs "
    "present in this tool's baked-in EUR 1000-Genomes-Phase3/HapMap3 "
    "reference panel contribute -- results reflect European-ancestry "
    "LD structure specifically. Never state a genetic correlation, "
    "heritability, or standard error this tool didn't actually "
    "compute.",
    {"trait1_sumstats": dict, "trait2_sumstats": dict},
)
async def estimate_genetic_correlation(args: dict[str, Any]) -> dict[str, Any]:
    trait1 = args.get("trait1_sumstats")
    trait2 = args.get("trait2_sumstats")
    for label, sumstats in (("trait1_sumstats", trait1), ("trait2_sumstats", trait2)):
        error = _validate_sumstats(sumstats, label)
        if error:
            return {"content": [{"type": "text", "text": error}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sumstats1_path = tmp_path / "trait1.sumstats.gz"
        sumstats2_path = tmp_path / "trait2.sumstats.gz"
        out_stem = tmp_path / "rg_result"

        _write_sumstats(trait1, sumstats1_path)
        _write_sumstats(trait2, sumstats2_path)

        code, out, err = await asyncio.to_thread(_run_ldsc_rg, sumstats1_path, sumstats2_path, out_stem)
        log_path = Path(f"{out_stem}.log")
        log_text = log_path.read_text() if log_path.exists() else ""

    # Real, confirmed-live wording bug: ldsc's actual log message for this
    # case is "After merging with reference panel LD, 0 SNPs remain."
    # (digit "0", not the word "No") -- neither substring check below
    # matched it, so this branch never fired for the exact real message
    # it exists to catch. Only reachable at all once ldsc.py's own
    # exception-logging bug is also patched (see Dockerfile's ldsc.py
    # sed fix) -- unpatched, that bug raised a secondary TypeError that
    # masked this message before it ever reached the log file.
    if "No SNPs remain" in log_text or "0 SNPs remain" in log_text or "no SNPs" in log_text.lower():
        return {"content": [{"type": "text", "text": "LDSC found no overlap between the given SNPs and the EUR 1000G-Phase3/HapMap3 reference panel -- use real dbSNP rsIDs present in HapMap3 to get a result."}]}

    match = None
    for line in log_text.splitlines():
        m = RG_MATCH.match(line)
        if m:
            match = m
            break

    if not match:
        return {"content": [{"type": "text", "text": f"LDSC did not produce a genetic-correlation estimate: {err.strip() or log_text[-2000:] or 'unknown error'}"}]}

    _, _, rg, se, z, p, h2_obs = match.groups()
    text = (
        f"LDSC genetic correlation (LD Score regression, EUR 1000G-Phase3/HapMap3 reference) "
        f"[ldsc:rg]:\nrg = {rg} (SE = {se}), Z = {z}, p = {p}"
    )
    return {"content": [{"type": "text", "text": text}]}


def build_ldsc_genetic_correlation_mcp_server():
    return create_sdk_mcp_server(name="ldsc_genetic_correlation", tools=[estimate_genetic_correlation])
