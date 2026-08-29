"""A real selscan MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Population genetics cluster) -- subprocess-wrapped `selscan`
CLI (real prebuilt static binary, see Dockerfile -- not apt/pip
installable, confirmed live). Real within-population haplotype-based
selection scan via nSL (number of Segregating sites by Length, Ferrer-
Admetlla et al. 2014).

Scoped to `--nsl`, not iHS/XP-EHH/XP-nSL: those need a genetic map
(--map, physical-to-genetic-distance data a chat caller can't
reasonably supply) or a second reference population; nSL is the one
selscan statistic that needs only phased haplotypes -- no external
map data -- while still giving a real per-site selection signal. Raw
(unstandardized) nSL is reported, not genome-wide-normalized (selscan's
companion `norm` tool needs a whole-chromosome scan to normalize
against, out of scope for a caller-supplied SNP set) -- stated plainly
rather than presented as a normalized score.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_SITES_RETURNED = 30


def _run_selscan(tped_path: Path, out_stem: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["selscan", "--nsl", "--tped", str(tped_path), "--out", str(out_stem)],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "scan_selection_nsl",
    "Given a dict of {sample_id: {\"hap1\": \"0101...\", \"hap2\": "
    "\"0110...\"}} (phased haplotypes, alleles coded 0/1, all samples "
    "and both haplotypes the same length, at least 4 diploid samples "
    "and 10 SNPs), compute real nSL (number of Segregating sites by "
    "Length) selection-scan scores per SNP via selscan -- a haplotype-"
    "length-based signal of recent positive selection within this "
    "sample set. Scores are raw/unstandardized (no genome-wide "
    "normalization, which needs a full-chromosome scan). Never state "
    "an nSL value this tool didn't actually compute.",
    {"samples": dict},
)
async def scan_selection_nsl(args: dict[str, Any]) -> dict[str, Any]:
    samples = args.get("samples")
    if not isinstance(samples, dict) or len(samples) < 4:
        return {"content": [{"type": "text", "text": "samples must be a dict of at least 4 {sample_id: {hap1, hap2}} entries -- nSL needs several haplotypes to be meaningful."}]}

    lengths = set()
    for sample_id, info in samples.items():
        if not isinstance(info, dict) or "hap1" not in info or "hap2" not in info:
            return {"content": [{"type": "text", "text": f"sample '{sample_id}' must have both 'hap1' and 'hap2' keys."}]}
        hap1, hap2 = info["hap1"], info["hap2"]
        if not (isinstance(hap1, str) and isinstance(hap2, str) and hap1 and hap2):
            return {"content": [{"type": "text", "text": f"sample '{sample_id}' hap1/hap2 must be non-empty strings."}]}
        if not set(hap1) <= {"0", "1"} or not set(hap2) <= {"0", "1"}:
            return {"content": [{"type": "text", "text": f"sample '{sample_id}' haplotypes must contain only '0'/'1' alleles."}]}
        lengths.add(len(hap1))
        lengths.add(len(hap2))
    if len(lengths) != 1:
        return {"content": [{"type": "text", "text": f"all haplotypes must be the same length -- got lengths {sorted(lengths)}."}]}
    n_snps = lengths.pop()
    if n_snps < 10:
        return {"content": [{"type": "text", "text": f"at least 10 SNPs are needed for a meaningful nSL scan -- got {n_snps}."}]}

    sample_ids = list(samples.keys())
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tped_path = tmp_path / "input.tped"
        out_stem = tmp_path / "result"

        # Real TPED format, confirmed against selscan's own README:
        # <chr> <locusID> <genetic_pos> <physical_pos> then two allele
        # columns per individual (one per haplotype). Genetic position
        # is unused by --nsl (no --map required for this statistic).
        lines = []
        for snp_idx in range(n_snps):
            row = ["1", f"snp{snp_idx}", "0", str((snp_idx + 1) * 1000)]
            for sid in sample_ids:
                row.append(samples[sid]["hap1"][snp_idx])
                row.append(samples[sid]["hap2"][snp_idx])
            lines.append(" ".join(row))
        tped_path.write_text("\n".join(lines) + "\n")

        code, out, err = await asyncio.to_thread(_run_selscan, tped_path, out_stem)
        nsl_path = Path(f"{out_stem}.nsl.out")
        nsl_text = nsl_path.read_text() if nsl_path.exists() else ""

    if not nsl_text.strip():
        return {"content": [{"type": "text", "text": f"selscan failed to produce nSL scores: {err.strip() or out.strip() or 'unknown error'}"}]}

    rows = [r.split() for r in nsl_text.strip().splitlines() if r.strip()]
    lines = [f"selscan nSL selection scan (raw/unstandardized) [selscan:nsl] -- {len(rows)} site(s):"]
    for row in rows[:MAX_SITES_RETURNED]:
        if len(row) < 6:
            continue
        locus_id, phys_pos, freq1, sl1, sl0, nsl_raw = row[:6]
        lines.append(f"- {locus_id} (pos {phys_pos}): freq(1)={freq1}, nSL(raw)={nsl_raw}")
    if len(rows) > MAX_SITES_RETURNED:
        lines.append(f"... and {len(rows) - MAX_SITES_RETURNED} more site(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_selscan_nsl_mcp_server():
    return create_sdk_mcp_server(name="selscan_nsl", tools=[scan_selection_nsl])
