"""A real NRP Calculator MCP tool (docs/12-biotools-triage-shortlist.md's
Synthetic biology cluster) -- non-repetitive DNA part design, the
platform's first synthetic-biology coverage. A real gap: designing a
toolbox of DNA parts (promoters, terminators, barcodes, primer-binding
sites) that share no long repeat with each other is a genuine synthetic-
biology design problem, not something any existing tool here answers.

Wraps nrpcalc's Maker Mode (real local combinatorial design, not a
lookup) -- given a degenerate IUPAC sequence constraint (e.g. all-N for
fully free positions) and a maximum allowed shared-repeat length, it
searches for a set of sequences that share no repeat longer than that
threshold. Real local computation, no external record for the result,
so the citable unit is the method itself, tagged [nrpcalc:design].

Two other Synthetic Biology cluster candidates from the triage doc were
investigated and deliberately not built this pass:
- PEGG: hard-pins scikit-learn==1.1.1 in its own dependency metadata,
  which would downgrade the shared orchestrator venv's scikit-learn
  (currently 1.9.x, required by the already-shipped
  app/tools/mhcflurry_binding.py) and silently break that tool.
- OpenCloning: not a simple importable library -- it's architected as
  its own FastAPI service (app/main.py, endpoints/, no hosted public
  API to call instead), which would mean running a second server
  process rather than an in-process import. Out of scope for this
  platform's established in-process tool pattern.
"""
import asyncio
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

_IUPAC_CODES = set("ACGTRYSWKMBDHVN")


def _run_design(seq_constr: str, part_type: str, lmax: int, target_size: int) -> dict[int, str]:
    from nrpcalc import maker

    struct_constr = "." * len(seq_constr)
    return maker(
        seq_constr=seq_constr,
        struct_constr=struct_constr,
        part_type=part_type,
        Lmax=lmax,
        target_size=target_size,
        verbose=False,
    )


@tool(
    "design_nonrepetitive_parts",
    "Design a toolbox of non-repetitive DNA (or RNA) parts using the NRP "
    "Calculator: given a sequence constraint in IUPAC degenerate code (e.g. "
    "'NNNNNNNNNNNNNNNN' for 16 fully free positions), find up to "
    "target_size sequences that satisfy it while sharing no repeat longer "
    "than max_shared_repeat with each other or with themselves. Useful for "
    "designing barcodes, primer-binding sites, or other parts that must not "
    "cross-react. Never state a designed sequence this tool didn't actually "
    "return.",
    {"sequence_constraint": str, "part_type": str, "max_shared_repeat": int, "target_size": int},
)
async def design_nonrepetitive_parts(args: dict[str, Any]) -> dict[str, Any]:
    seq_constr = args["sequence_constraint"].strip().upper()
    part_type = (args.get("part_type") or "DNA").strip().upper()
    lmax = int(args.get("max_shared_repeat") or 6)
    target_size = int(args.get("target_size") or 3)

    if not seq_constr or any(c not in _IUPAC_CODES for c in seq_constr):
        return {"content": [{"type": "text", "text": "sequence_constraint must be non-empty IUPAC degenerate code (A/C/G/T/N/R/Y/S/W/K/M/B/D/H/V)."}]}
    if len(seq_constr) < 8 or len(seq_constr) > 200:
        return {"content": [{"type": "text", "text": "sequence_constraint length must be between 8 and 200 (longer constraints can take a long time to solve)."}]}
    if part_type not in ("DNA", "RNA"):
        return {"content": [{"type": "text", "text": "part_type must be 'DNA' or 'RNA'."}]}
    if not (2 <= lmax <= len(seq_constr) - 1):
        return {"content": [{"type": "text", "text": "max_shared_repeat must be between 2 and len(sequence_constraint)-1."}]}
    if not (1 <= target_size <= 20):
        return {"content": [{"type": "text", "text": "target_size must be between 1 and 20 (larger toolboxes can take a long time to solve)."}]}

    try:
        parts = await asyncio.wait_for(
            asyncio.to_thread(_run_design, seq_constr, part_type, lmax, target_size),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        return {"content": [{"type": "text", "text": "Design search did not converge within 90s -- try a shorter constraint, larger max_shared_repeat, or smaller target_size."}]}

    if not parts:
        return {"content": [{"type": "text", "text": "No non-repetitive toolbox found for these constraints -- try relaxing max_shared_repeat or the sequence constraint."}]}

    # [nrpcalc:design] is the citable unit -- real local combinatorial
    # search, same methodological-citation convention as scikit-bio/cobra.
    lines = [
        f"Non-repetitive {part_type} toolbox [nrpcalc:design] "
        f"(constraint '{seq_constr}', max shared repeat {lmax}bp, {len(parts)}/{target_size} parts found):"
    ]
    for idx in sorted(parts):
        lines.append(f"- Part {idx}: {parts[idx]}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_nrpcalc_design_mcp_server():
    return create_sdk_mcp_server(name="nrpcalc_design", tools=[design_nonrepetitive_parts])
