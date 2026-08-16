"""A real scikit-bio MCP tool (docs/10-build-plan.md Phase 5 -- the first
result of the bio.tools + GitHub-repo triage: scikit-bio (969+ GitHub
stars, actively maintained, general-purpose) was picked over the
33,110-entry bio.tools long tail's near-entirely single-paper research
code, which mostly needs the sandboxed tool-runner (Phase 6) this tool
deliberately avoids needing.

Unlike every other tool source so far, this runs a real local
computation (in-process, via the scikit-bio package installed into the
orchestrator's own venv) rather than calling an external API -- no
network dependency, no rate limits, no external outage risk. It fills a
domain this platform had zero coverage in: microbiome/community
ecology diversity metrics.

One tool: alpha diversity (within-sample diversity) on a taxon
abundance table -- the standard first-pass microbiome-composition
analysis. Beta diversity (between-sample) and other scikit-bio
capabilities (sequence alignment, phylogenetics) are natural follow-ups
once this pattern is proven, not built speculatively now.
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from skbio.diversity import alpha_diversity

# metric name -> (skbio metric id, human label)
METRICS = {
    "shannon": ("shannon", "Shannon diversity index (accounts for both richness and evenness)"),
    "simpson": ("simpson", "Simpson diversity index (probability two random individuals differ)"),
    "richness": ("sobs", "Observed species richness (count of taxa with nonzero abundance)"),
}


@tool(
    "compute_diversity_metrics",
    "Given a taxon abundance table for one sample (a list of counts, "
    "optionally with matching taxon labels), compute alpha diversity "
    "metrics (Shannon, Simpson, observed richness) via scikit-bio -- the "
    "standard first-pass microbiome-composition analysis. Never state a "
    "diversity value this tool didn't actually compute.",
    {"counts": list, "taxon_labels": list, "metrics": list},
)
async def compute_diversity_metrics(args: dict[str, Any]) -> dict[str, Any]:
    counts = [int(c) for c in args["counts"]]
    if not counts or all(c == 0 for c in counts):
        return {"content": [{"type": "text", "text": "counts must contain at least one nonzero abundance value."}]}
    labels = args.get("taxon_labels") or [f"taxon_{i}" for i in range(len(counts))]
    if len(labels) != len(counts):
        return {"content": [{"type": "text", "text": "taxon_labels, if given, must be the same length as counts."}]}

    requested = args.get("metrics") or list(METRICS.keys())
    unknown = [m for m in requested if m not in METRICS]
    if unknown:
        return {"content": [{"type": "text", "text": f"Unknown metric(s) {unknown} -- choose from {list(METRICS.keys())}."}]}

    # [scikit-bio:metric] is the citable unit -- like huggingface.py, this
    # is a real local computation on caller-supplied data, not an
    # external database record, so what's citable is which method
    # actually produced the number (claude_runner.py's
    # RECORD_REF_PATTERNS matches this the same way).
    lines = [f"Diversity metrics for {len(counts)} taxa ({sum(counts)} total counts):"]
    for m in requested:
        skbio_id, description = METRICS[m]
        value = float(alpha_diversity(skbio_id, [counts]).iloc[0])
        lines.append(f"- {description} [scikit-bio:{m}]: {value:.4f}")

    nonzero = [(l, c) for l, c in zip(labels, counts) if c > 0]
    lines.append(f"Present taxa: {', '.join(f'{l} ({c})' for l, c in nonzero)}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_scikit_bio_mcp_server():
    return create_sdk_mcp_server(name="scikit_bio", tools=[compute_diversity_metrics])
