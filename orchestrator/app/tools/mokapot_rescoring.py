"""A real mokapot MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
1, Proteomics cluster) -- real semi-supervised PSM (peptide-spectrum
match) rescoring for FDR control, pairing with the already-live
`pyteomics_mass` tool (peptide mass/fragment calculation): pyteomics_mass
answers "what mass should this peptide have", mokapot answers "given a
real search engine's PSM scores, which identifications actually pass a
target false-discovery-rate threshold" -- the standard next step after
any database-search proteomics workflow.

Wraps `mokapot.LinearPsmDataset` + `mokapot.brew` directly on a caller-
supplied PSM table (target/decoy flag + one or more search-engine
feature scores per spectrum) rather than requiring a Percolator/pin file
on disk -- matches this platform's "real local computation on caller-
supplied data" pattern (scikit_bio, tcrdist_repertoire, egglib_popgen).
Confirmed live that mokapot's target-column handling is `.astype(bool)`,
not a +1/-1 encoding some search-engine PSM formats use -- caller input
here is normalized to real booleans before being handed to mokapot.
"""
from typing import Any

import mokapot
import pandas as pd
from claude_agent_sdk import create_sdk_mcp_server, tool


@tool(
    "rescore_psms",
    "Given a list of PSM (peptide-spectrum match) records -- each with "
    "spectrum_id, peptide, is_target (bool: True for a real/target match, "
    "False for a decoy/null match used to estimate the false-discovery "
    "rate), and one or more numeric search-engine scores (as extra "
    "fields, e.g. 'xcorr', 'mass_error') -- run mokapot's real semi-"
    "supervised rescoring and return each PSM's mokapot score and q-value "
    "(the FDR-controlled significance). Needs a real, reasonably large "
    "PSM set (hundreds+) with both targets and decoys present -- this is "
    "a real statistical procedure, not a lookup. Never state a q-value "
    "this tool didn't actually compute.",
    {"psms": list, "target_fdr": float},
)
async def rescore_psms(args: dict[str, Any]) -> dict[str, Any]:
    psms = args.get("psms")
    target_fdr = float(args.get("target_fdr", 0.05))
    if not isinstance(psms, list) or len(psms) < 20:
        return {"content": [{"type": "text", "text": "psms must be a list of at least 20 PSM records (mokapot's rescoring needs a real-sized dataset, not a handful)."}]}

    required = {"spectrum_id", "peptide", "is_target"}
    feature_keys: set[str] = set()
    for i, p in enumerate(psms):
        missing = required - p.keys()
        if missing:
            return {"content": [{"type": "text", "text": f"PSM at index {i} is missing required field(s): {sorted(missing)}."}]}
        feature_keys |= (p.keys() - required)
    if not feature_keys:
        return {"content": [{"type": "text", "text": "Each PSM needs at least one numeric search-engine score field beyond spectrum_id/peptide/is_target."}]}
    feature_keys_sorted = sorted(feature_keys)

    df = pd.DataFrame(
        {
            "SpecId": [p["spectrum_id"] for p in psms],
            "Peptide": [p["peptide"] for p in psms],
            "Label": [bool(p["is_target"]) for p in psms],
            **{f: [float(p.get(f, 0.0)) for p in psms] for f in feature_keys_sorted},
        }
    )

    try:
        dataset = mokapot.LinearPsmDataset(
            psms=df,
            target_column="Label",
            spectrum_columns="SpecId",
            peptide_column="Peptide",
            feature_columns=feature_keys_sorted,
        )
        results, _models = mokapot.brew(dataset, test_fdr=target_fdr)
    except Exception as exc:  # noqa: BLE001 -- surface real mokapot errors (e.g. too few decoys) to the caller
        return {"content": [{"type": "text", "text": f"mokapot rescoring failed: {exc}"}]}

    scored = results.psms.sort_values("mokapot q-value")
    passing = (scored["mokapot q-value"] <= target_fdr).sum()

    # [mokapot:target_fdr] is the citable unit -- real local computation
    # on caller-supplied data, same methodological-citation convention as
    # cobra/scikit-bio/tcrdist.
    lines = [
        f"mokapot PSM rescoring [mokapot:{target_fdr}] -- {len(scored)} PSMs, "
        f"{int(passing)} pass q <= {target_fdr}:"
    ]
    for _, row in scored.head(20).iterrows():
        lines.append(
            f"- {row['Peptide']} ({row['SpecId']}): mokapot score {row['mokapot score']:.4f}, "
            f"q-value {row['mokapot q-value']:.4g}"
        )
    if len(scored) > 20:
        lines.append(f"... ({len(scored) - 20} more, sorted by q-value)")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_mokapot_rescoring_mcp_server():
    return create_sdk_mcp_server(name="mokapot_rescoring", tools=[rescore_psms])
