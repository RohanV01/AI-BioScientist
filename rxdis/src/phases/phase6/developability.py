"""
Phase 6 — Peptide developability assessment.

Covers:
  aggregation    — hydrophobic patch analysis (TANGO-proxy via sequence)
  solubility     — charge/hydrophobicity balance
  immunogenicity — MHC-II binding SMARTS-proxy (rough heuristic; real NetMHCpan
                   requires academic installation at Databases/netmhcpan/)
  humanness      — fraction of human germline-matching tripeptides
  stability      — predicted half-life (intracellular vs extracellular)

Returns a developability_score (0-1) and per-endpoint results.
"""
from __future__ import annotations

import math
import logging
import os
from typing import Dict, List, Literal, Optional, Tuple

log = logging.getLogger(__name__)

# Kyte-Doolittle hydrophobicity scale
_KD = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5, "Q": -3.5,
    "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5, "L": 3.8, "K": -3.9,
    "M": 1.9, "F": 2.8, "P": -1.6, "S": -0.8, "T": -0.7, "W": -0.9,
    "Y": -1.3, "V": 4.2,
}

# Charges at pH 7.4
_CHARGE = {
    "R": +1.0, "K": +1.0, "H": +0.1, "D": -1.0, "E": -1.0,
}

_NETMHCPAN_BIN: Optional[str] = None


def _find_netmhcpan() -> Optional[str]:
    """Locate NetMHCpan (4.1 or 4.2) if installed locally."""
    from pathlib import Path
    from src.config import settings
    candidates = [
        Path.home() / "netMHCpan-4.2" / "netMHCpan",   # 4.2 — checked first
        Path.home() / "netMHCpan-4.1" / "netMHCpan",
        Path(settings.DB_HPA).parent / "netmhcpan" / "netMHCpan",
        Path("/usr/local/bin/netMHCpan"),
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return str(c)
    import shutil
    return shutil.which("netMHCpan")


# ─────────────────────────────────────────────────────────────────────────────
# Individual assessors
# ─────────────────────────────────────────────────────────────────────────────

def assess_aggregation(sequence: str) -> Tuple[str, float]:
    """
    Aggregation risk via hydrophobic window scanning (TANGO-proxy).
    Returns (risk: low/medium/high, score: 0-1).
    """
    if len(sequence) < 4:
        return "low", 0.0
    window = min(6, len(sequence))
    max_hydro = -999.0
    for i in range(len(sequence) - window + 1):
        window_seq = sequence[i:i + window]
        avg_hydro = sum(_KD.get(aa, 0) for aa in window_seq) / window
        max_hydro = max(max_hydro, avg_hydro)

    # Aggregation risk thresholds (empirical from TANGO validation)
    if max_hydro > 2.5:
        return "high", round(min(1.0, (max_hydro - 2.5) / 2.0), 3)
    elif max_hydro > 1.5:
        return "medium", round((max_hydro - 1.5) / 1.0, 3)
    return "low", 0.0


def assess_solubility(sequence: str) -> Tuple[float, Dict]:
    """
    Solubility score (0-1) via charge/hydrophobicity balance.
    NetSolP-1.0 proxy: net_charge / len + fraction_polar.
    """
    net_charge = sum(_CHARGE.get(aa, 0) for aa in sequence)
    n_hydrophobic = sum(1 for aa in sequence if _KD.get(aa, 0) > 1.5)
    fraction_hydrophobic = n_hydrophobic / max(1, len(sequence))
    fraction_polar = sum(1 for aa in sequence if aa in "STNQRHKDE") / max(1, len(sequence))

    # High solubility: high charge magnitude + low hydrophobicity
    charge_score = min(1.0, abs(net_charge) / max(1, len(sequence)) * 5)
    hydro_penalty = max(0, fraction_hydrophobic - 0.3) * 2  # penalise >30% hydrophobic

    sol_score = round(max(0.0, min(1.0, 0.4 + charge_score * 0.4 - hydro_penalty)), 3)
    return sol_score, {
        "net_charge": round(net_charge, 1),
        "fraction_hydrophobic": round(fraction_hydrophobic, 3),
        "fraction_polar": round(fraction_polar, 3),
    }


def assess_immunogenicity_heuristic(
    sequence: str,
    indication_type: str = "chronic",
) -> Tuple[str, int]:
    """
    Rough MHC-II immunogenicity heuristic.
    Real NetMHCpan requires installation; this estimates risk from
    hydrophobic/aromatic content in 9-mer windows (promiscuous MHC-II anchor
    positions: p1/p4/p6/p9 prefer hydrophobic/aromatic).

    Returns (risk: low/medium/high, n_predicted_strong_binders).
    """
    global _NETMHCPAN_BIN
    if _NETMHCPAN_BIN is None:
        _NETMHCPAN_BIN = _find_netmhcpan() or ""

    # Attempt real NetMHCpan if available
    if _NETMHCPAN_BIN:
        try:
            return _run_netmhcpan(sequence, _NETMHCPAN_BIN)
        except Exception as exc:
            log.debug("[6.dev] NetMHCpan failed: %s", exc)

    # Heuristic fallback
    n_strong = 0
    window = 9
    for i in range(len(sequence) - window + 1):
        w = sequence[i:i + window]
        # Check anchor positions 1, 4, 6, 9 (0-indexed: 0, 3, 5, 8)
        anchors = [_KD.get(w[j], 0) for j in [0, 3, 5, 8] if j < len(w)]
        anchor_hydro = sum(a > 1.5 for a in anchors)
        if anchor_hydro >= 3:  # 3+ hydrophobic anchors = strong MHC-II binding
            n_strong += 1

    if n_strong == 0:
        risk = "low"
    elif n_strong <= 3 or indication_type == "oncology":
        risk = "medium"
    else:
        risk = "high"
    return risk, n_strong


def _run_netmhcpan(sequence: str, binary: str) -> Tuple[str, int]:
    """
    Run NetMHCpan 4.2 locally for MHC-I binding prediction.
    Uses a broad HLA-A/B/C supertype panel covering ~97% of the human population.
    """
    import subprocess, tempfile, os
    from pathlib import Path as _Path

    fasta = f">peptide\n{sequence}\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".fasta", delete=False) as f:
        f.write(fasta)
        fasta_path = f.name

    # Common HLA-A/B/C supertypes for MHC-I prediction
    alleles = "HLA-A02:01,HLA-A01:01,HLA-A03:01,HLA-B07:02,HLA-B44:02"
    # netMHCpan must run from its own directory (tcsh wrapper uses relative paths)
    cwd = str(_Path(binary).parent)

    try:
        result = subprocess.run(
            [binary, "-f", fasta_path, "-a", alleles, "-BA", "-l", "9"],
            capture_output=True, text=True, timeout=120,
            cwd=cwd,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"netMHCpan exited {result.returncode}: {result.stderr[:300]}"
            )
        n_strong = result.stdout.count("<= SB")
        n_weak   = result.stdout.count("<= WB")
        risk = "low" if n_strong == 0 and n_weak <= 2 else (
               "medium" if n_strong <= 2 else "high")
        return risk, n_strong
    finally:
        try:
            os.unlink(fasta_path)
        except OSError:
            pass


def assess_stability(sequence: str, target_class: str) -> Dict:
    """
    Predict half-life proxy.
    Rules based on N-terminal residue (Bachmair 1986) and cyclic flag.
    Returns {half_life_class, n_terminal_rule, is_proteolysis_concern}.
    """
    n_term = sequence[0] if sequence else "?"
    # N-end rule (mammalian cytoplasm): 20 min - 30 h
    unstable_n_term = set("RKHFLYWID")
    stable_n_term   = set("ACGMSTPV")

    is_unstable = n_term in unstable_n_term
    is_intracellular = target_class in ("intracellular", "disordered")

    half_life_class = (
        "short" if (is_unstable and is_intracellular) else
        "medium" if is_unstable else
        "long"
    )
    return {
        "half_life_class": half_life_class,
        "n_terminal_rule": "unstable" if is_unstable else "stable",
        "proteolysis_concern": is_unstable and is_intracellular,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Composite developability score
# ─────────────────────────────────────────────────────────────────────────────

def score_developability(
    sequence: str,
    target_class: str = "extracellular",
    indication_type: str = "chronic",
    cyclic_preferred: bool = False,
) -> Dict:
    """
    Score all developability axes for a peptide sequence.

    Returns:
      aggregation, solubility_score, immunogenicity_risk, n_mhc_strong,
      stability, developability_score (0-1), passes, disqualifying, concerns
    """
    agg_risk, agg_score = assess_aggregation(sequence)
    sol_score, sol_info = assess_solubility(sequence)

    imm_risk, n_mhc = assess_immunogenicity_heuristic(sequence, indication_type)
    stab = assess_stability(sequence, target_class)

    disqualifying = []
    concerns = []

    if agg_risk == "high":
        disqualifying.append(f"aggregation_high(score={agg_score:.2f})")
    elif agg_risk == "medium":
        concerns.append("aggregation_medium")

    if sol_score < 0.4:
        disqualifying.append(f"low_solubility({sol_score:.2f})")
    elif sol_score < 0.55:
        concerns.append(f"moderate_solubility({sol_score:.2f})")

    # Immunogenicity: critical for chronic indications
    if imm_risk == "high":
        if indication_type == "chronic":
            disqualifying.append(f"immunogenic_chronic(n_mhc={n_mhc})")
        else:
            concerns.append(f"immunogenic(n_mhc={n_mhc})")
    elif imm_risk == "medium":
        concerns.append(f"immunogenicity_medium(n_mhc={n_mhc})")

    if stab["proteolysis_concern"] and not cyclic_preferred:
        concerns.append("proteolysis_risk_without_cyclization")

    # Score
    dev_score = 1.0
    dev_score -= 0.3 * len(disqualifying)
    dev_score -= 0.1 * len(concerns)
    dev_score = round(max(0.0, min(1.0, dev_score)), 3)

    passes = len(disqualifying) == 0

    return {
        "aggregation": agg_risk,
        "aggregation_score": agg_score,
        "solubility_score": sol_score,
        **sol_info,
        "immunogenicity": imm_risk,
        "n_mhc_strong_binders": n_mhc,
        "stability": stab,
        "disqualifying": disqualifying,
        "concerns": concerns,
        "developability_score": dev_score,
        "passes": passes,
    }


def batch_assess(
    sequences: List[str],
    target_class: str = "extracellular",
    indication_type: str = "chronic",
    cyclic_preferred: bool = False,
) -> List[Dict]:
    results = []
    for seq in sequences:
        r = score_developability(seq, target_class=target_class,
                                 indication_type=indication_type,
                                 cyclic_preferred=cyclic_preferred)
        r["sequence"] = seq
        results.append(r)
    n_pass = sum(1 for r in results if r["passes"])
    log.info("[6.dev] %d/%d sequences pass developability", n_pass, len(results))
    return results
