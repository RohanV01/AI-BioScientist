"""A real tcrdist3 MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1, Immunoinformatics cluster) -- real local TCR-TCR distance
computation via `tcrdist.repertoire.TCRrep`, no external API, no model
download. Fills a domain this platform had zero coverage in: T-cell
receptor repertoire comparison (which TCRs in a set are similar enough to
plausibly recognize the same antigen).

One tool: given a list of beta-chain TCRs (CDR3 amino acid sequence, V
gene, J gene), compute the pairwise TCRdist distance matrix -- the
standard first-pass repertoire-clustering input.
"""
from typing import Any

import pandas as pd
from claude_agent_sdk import create_sdk_mcp_server, tool
from tcrdist.repertoire import TCRrep


@tool(
    "compute_tcr_distances",
    "Given a list of beta-chain TCRs, each with cdr3_b_aa (CDR3 amino "
    "acid sequence), v_b_gene, and j_b_gene (IMGT gene names, e.g. "
    "'TRBV5-1*01'), compute the real pairwise TCRdist distance matrix via "
    "tcrdist3 -- lower distance means more likely to recognize the same "
    "antigen. Requires at least 2 TCRs. Never state a distance this tool "
    "didn't actually compute.",
    {"tcrs": list},
)
async def compute_tcr_distances(args: dict[str, Any]) -> dict[str, Any]:
    tcrs = args.get("tcrs")
    if not isinstance(tcrs, list) or len(tcrs) < 2:
        return {"content": [{"type": "text", "text": "tcrs must be a list of at least 2 TCR records."}]}

    required = {"cdr3_b_aa", "v_b_gene", "j_b_gene"}
    for i, t in enumerate(tcrs):
        missing = required - t.keys()
        if missing:
            return {"content": [{"type": "text", "text": f"TCR at index {i} is missing required field(s): {sorted(missing)}."}]}

    df = pd.DataFrame(
        {
            "cdr3_b_aa": [t["cdr3_b_aa"] for t in tcrs],
            "v_b_gene": [t["v_b_gene"] for t in tcrs],
            "j_b_gene": [t["j_b_gene"] for t in tcrs],
            "count": [1] * len(tcrs),
            "subject": ["query"] * len(tcrs),
        }
    )

    try:
        tr = TCRrep(cell_df=df, organism="human", chains=["beta"])
    except Exception as exc:  # noqa: BLE001 -- surface real tcrdist3 errors (e.g. unrecognized gene name)
        return {"content": [{"type": "text", "text": f"tcrdist3 computation failed: {exc}"}]}

    matrix = tr.pw_beta
    labels = [f"{t['v_b_gene']}/{t['cdr3_b_aa']}" for t in tcrs]

    # [tcrdist:beta] is the citable unit -- real local computation, same
    # methodological-citation convention as scikit-bio/cobra/vina.
    lines = [f"TCRdist pairwise beta-chain distance matrix [tcrdist:beta] ({len(tcrs)} TCRs):"]
    lines.append("   " + " | ".join(labels))
    for label, row in zip(labels, matrix):
        lines.append(f"- {label}: " + ", ".join(str(int(v)) for v in row))
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_tcrdist_repertoire_mcp_server():
    return create_sdk_mcp_server(name="tcrdist_repertoire", tools=[compute_tcr_distances])
