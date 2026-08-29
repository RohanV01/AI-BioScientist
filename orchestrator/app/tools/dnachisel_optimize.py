"""A real codon-optimization MCP tool (docs/17-remaining-tools-wiring-
plan.md Phase 2, Synthetic biology cluster) via `dnachisel`
(Edinburgh Genome Foundry's constraint-based DNA sequence design
engine), confirmed live before wiring (real optimized output produced,
translation-preservation/GC-content/restriction-site constraints all
verified passing).

Wired in place of the docs/12-listed "bebop/poly" -- that project
(github.com/bebop/poly) is a Go *library* with no CLI or prebuilt
binary (`go get github.com/bebop/poly`, meant to be imported into a Go
program), so using it here would mean introducing an entirely new
compiled-language toolchain into this Python-first codebase just to
wrap a thin custom Go binary. dnachisel is a genuinely PyPI-installable
pure-Python substitute for poly's codon-optimization capability
specifically -- its other two listed capabilities (primers, part
assembly) are already covered by this platform's `primer3` and
`gibson_assembly` tools, so no coverage is actually lost.
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from dnachisel import AvoidPattern, CodonOptimize, DnaOptimizationProblem, EnforceGCContent, EnforceTranslation

VALID_SPECIES = {"e_coli", "h_sapiens", "s_cerevisiae", "b_subtilis"}
MAX_SEQUENCE_LENGTH = 3000


@tool(
    "optimize_codon_usage",
    "Given a coding DNA sequence (length a multiple of 3, valid start/"
    "stop codon) and a target expression host (one of: e_coli, "
    "h_sapiens, s_cerevisiae, b_subtilis), re-encode it via real "
    "constraint-based codon optimization (dnachisel) to better match "
    "that host's codon usage while preserving the exact same protein "
    "translation, avoiding common restriction sites (BsaI, BsmBI), and "
    "keeping GC content in a workable 30-70% range. Never state an "
    "optimized sequence this tool didn't actually compute, and never "
    "claim it preserves translation without the tool's own "
    "confirmation.",
    {"sequence": str, "species": str},
)
async def optimize_codon_usage(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    species = args.get("species") or "e_coli"
    if species not in VALID_SPECIES:
        return {"content": [{"type": "text", "text": f"species must be one of {sorted(VALID_SPECIES)}."}]}
    if not sequence or len(sequence) % 3 != 0:
        return {"content": [{"type": "text", "text": "sequence must be a non-empty coding DNA sequence with length a multiple of 3."}]}
    if len(sequence) > MAX_SEQUENCE_LENGTH:
        return {"content": [{"type": "text", "text": f"sequence is {len(sequence)}bp -- at most {MAX_SEQUENCE_LENGTH}bp for a tractable optimization here."}]}
    if not set(sequence) <= set("ACGT"):
        return {"content": [{"type": "text", "text": "sequence must contain only A/C/G/T."}]}

    try:
        problem = DnaOptimizationProblem(
            sequence=sequence,
            constraints=[
                EnforceTranslation(),
                EnforceGCContent(mini=0.3, maxi=0.7),
                AvoidPattern("BsaI_site"),
                AvoidPattern("BsmBI_site"),
            ],
            objectives=[CodonOptimize(species=species)],
        )
        problem.resolve_constraints()
        problem.optimize()
    except Exception as exc:  # noqa: BLE001 -- surface real dnachisel constraint/optimization errors to the caller
        return {"content": [{"type": "text", "text": f"Codon optimization failed: {exc}"}]}

    all_passed = problem.all_constraints_pass()

    lines = [
        f"dnachisel codon optimization for {species} [dnachisel:optimized]:",
        f"Original:  {sequence}",
        f"Optimized: {problem.sequence}",
        f"All constraints (translation preserved, GC 30-70%, no BsaI/BsmBI sites) passed: {all_passed}",
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_dnachisel_optimize_mcp_server():
    return create_sdk_mcp_server(name="dnachisel_optimize", tools=[optimize_codon_usage])
