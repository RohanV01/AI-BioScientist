"""A real PAML MCP tool (docs/17-remaining-tools-wiring-plan.md Phase 2,
Phylogenetics cluster) -- subprocess-wrapped `yn00` CLI (apt `paml`
package, see Dockerfile), real pairwise dN/dS (nonsynonymous/synonymous
substitution rate ratio, omega) estimation via Yang & Nielsen (2000)
between coding sequences.

Scoped to yn00, not codeml: codeml's site/branch-model ML analysis
needs a caller-supplied tree topology and per-model config the caller
can't reasonably provide in a chat turn; yn00 needs only a codon
alignment and gives the same real omega estimate for the common
question ("is this gene under positive/purifying selection between
these sequences?") without that extra input. Real gap this platform
had zero coverage of -- nothing else here computes dN/dS.
"""
import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

# Real yn00 control-file format, confirmed against PAML's own
# examples/yn00.ctl (github.com/abacus-gene/paml) rather than guessed.
YN00_CTL_TEMPLATE = """\
      seqfile = {seqfile}
      outfile = {outfile}
      verbose = 0
        icode = 0
    weighting = 0
   commonf3x4 = 0
"""

# Matches rows of the "Pairwise estimation by the method of Yang &
# Nielsen (2000) (equal weighting of pathways)" table in yn00's output
# file. Real, confirmed-live format (via cat -A on a real run's out.txt),
# NOT the naive 9-plain-numbers shape this used to assume: dN and dS are
# each a "value +- SE" pair (matching the header's own "dN +- SE    dS
# +- SE" columns), e.g.
#   2    1    34.7    82.3   2.3650  4.6000  0.0000 -0.0000 +- 0.0000  2.6596 +- 2.6194
YN00_ROW = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.-]+)"
    r"\s+([\d.-]+)\s*\+-\s*([\d.]+)\s+([\d.-]+)\s*\+-\s*([\d.]+)\s*$"
)


def _run_yn00(seq_path: Path, out_path: Path, ctl_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(["yn00", ctl_path.name], capture_output=True, text=True, timeout=60, cwd=str(ctl_path.parent))
    return proc.returncode, proc.stdout, proc.stderr


def _validate_codon_sequences(sequences: dict) -> str | None:
    if not isinstance(sequences, dict) or len(sequences) < 2:
        return "sequences must be a dict of at least 2 {name: coding_sequence} pairs."
    if len(sequences) > 8:
        return "at most 8 sequences at a time -- pairwise comparisons grow quadratically."
    lengths = {len(v) for v in sequences.values()}
    if len(lengths) != 1:
        return f"all sequences must be the same length (codon-aligned) -- got lengths {sorted(lengths)}."
    length = lengths.pop()
    if length % 3 != 0 or length == 0:
        return f"sequence length must be a nonzero multiple of 3 (codons) -- got {length}."
    for name, seq in sequences.items():
        if not set(seq.upper()) <= set("ACGT"):
            return f"sequence '{name}' contains non-ACGT characters -- yn00 needs ungapped coding DNA."
    return None


@tool(
    "estimate_dnds",
    "Given a dict of {sequence_name: coding_sequence} (DNA, in-frame, "
    "codon-aligned, no gaps, at least 2 and at most 8 sequences), compute "
    "real pairwise dN/dS (omega, the nonsynonymous/synonymous "
    "substitution rate ratio) via PAML's yn00 (Yang & Nielsen 2000 "
    "method) for every sequence pair. omega > 1 suggests positive "
    "(diversifying) selection, omega < 1 purifying selection, omega ~= 1 "
    "neutral. Never state a dN, dS, or omega value this tool didn't "
    "actually compute.",
    {"sequences": dict},
)
async def estimate_dnds(args: dict[str, Any]) -> dict[str, Any]:
    sequences = args.get("sequences")
    error = _validate_codon_sequences(sequences)
    if error:
        return {"content": [{"type": "text", "text": error}]}

    names = list(sequences.keys())
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        seq_path = tmp_path / "seqs.phy"
        out_path = tmp_path / "yn.out"
        ctl_path = tmp_path / "yn00.ctl"

        # Real, confirmed-live format bug: yn00's sequential PHYLIP reader
        # expects the name and its sequence on the SAME line, separated
        # by 2+ spaces ("Make sure to separate the sequence from its
        # name by 2 or more spaces" is yn00's own literal error message
        # for exactly the name-then-sequence-on-separate-lines layout
        # this used to write) -- not name on one line, sequence on the
        # next. Verified live: this same input, reformatted this way,
        # produces yn00's real "equal weighting of pathways" table with
        # real dN/dS/omega values.
        length = len(next(iter(sequences.values())))
        lines = [f" {len(sequences)} {length}"]
        for name in names:
            lines.append(f"{name}  {sequences[name].upper()}")
        seq_path.write_text("\n".join(lines) + "\n")
        ctl_path.write_text(YN00_CTL_TEMPLATE.format(seqfile=seq_path.name, outfile=out_path.name))

        code, out, err = await asyncio.to_thread(_run_yn00, seq_path, out_path, ctl_path)
        result_text = out_path.read_text() if out_path.exists() else ""

    if not result_text.strip():
        return {"content": [{"type": "text", "text": f"yn00 failed to produce output: {err.strip() or out.strip() or 'unknown error'}"}]}

    # Isolate the "(equal weighting of pathways)" YN00 table -- the
    # method this tool is named for, not the Nei-Gojobori or ML tables
    # yn00 also prints in the same file.
    marker = "equal weighting of pathways"
    idx = result_text.find(marker)
    if idx == -1:
        return {"content": [{"type": "text", "text": f"Could not find YN00 results table in yn00 output:\n{result_text[:2000]}"}]}
    table_text = result_text[idx:]

    rows = []
    for line in table_text.splitlines():
        m = YN00_ROW.match(line)
        if m:
            i2, i1, s, n, t, kappa, omega, dn, dn_se, ds, ds_se = m.groups()
            rows.append((int(i2) - 1, int(i1) - 1, float(omega), float(dn), float(ds)))

    if not rows:
        return {"content": [{"type": "text", "text": f"yn00 ran but no pairwise estimates were parsed:\n{table_text[:2000]}"}]}

    lines = [f"PAML yn00 pairwise dN/dS estimates (Yang & Nielsen 2000) [paml:yn00]:"]
    for i2, i1, omega, dn, ds in rows:
        lines.append(f"- {names[i2]} vs {names[i1]}: omega (dN/dS) = {omega:.4f}, dN = {dn:.4f}, dS = {ds:.4f}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_paml_yn00_mcp_server():
    return create_sdk_mcp_server(name="paml_yn00", tools=[estimate_dnds])
