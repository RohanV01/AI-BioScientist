"""
Phase 6 — Local replacements for Neurosnap API tools.

Previously called Neurosnap cloud APIs (BoltzGen, Boltz-2, Aggrescan3D, NetSolP).
Now runs fully locally — no API key needed.

  BoltzGen / backbone gen  →  local RFdiffusion (via nim_rfdiffusion.run_rfdiffusion_nim)
  Boltz-2 refolding        →  local Boltz-1 CPU (via nim_rfdiffusion.score_af2_nim)
  Aggrescan3D              →  hydrophobic window scan heuristic (no install needed)
  NetSolP                  →  charge/hydrophobicity balance heuristic (no install needed)
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# Kyte-Doolittle hydrophobicity
_KD = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5, "Q": -3.5,
    "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5, "L": 3.8, "K": -3.9,
    "M": 1.9, "F": 2.8, "P": -1.6, "S": -0.8, "T": -0.7, "W": -0.9,
    "Y": -1.3, "V": 4.2,
}
_CHARGE = {"R": 1.0, "K": 1.0, "H": 0.1, "D": -1.0, "E": -1.0}


# ─────────────────────────────────────────────────────────────────────────────
# BoltzGen → local RFdiffusion
# ─────────────────────────────────────────────────────────────────────────────

def run_boltzgen(
    interface_ctx: Dict,
    n_designs: int = 50,
    api_key: str = "",          # unused — kept for call-site compatibility
) -> List[str]:
    """
    Generate backbone sequences via local RFdiffusion.
    Returns [] if RFdiffusion is not installed.
    """
    from .nim_rfdiffusion import run_rfdiffusion_nim
    return run_rfdiffusion_nim(interface_ctx, n_backbones=n_designs)


# ─────────────────────────────────────────────────────────────────────────────
# Boltz-2 refolding → local Boltz-1
# ─────────────────────────────────────────────────────────────────────────────

def score_refolding(
    target_pdb_url: str,
    binder_sequence: str,
    api_key: str = "",          # unused — kept for call-site compatibility
) -> Optional[Dict]:
    """
    Score binder-target complex via local Boltz-1 in CPU mode.
    Returns {iptm, pae_interface, binder_plddt, passes, source} or None.
    """
    from .nim_rfdiffusion import score_af2_nim
    result = score_af2_nim(target_pdb_url, binder_sequence)
    if result:
        result["source"] = "boltz1_local_cpu"
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Aggrescan3D → local hydrophobic window scan
# ─────────────────────────────────────────────────────────────────────────────

def score_aggrescan3d(
    sequence: str,
    api_key: str = "",          # unused — kept for call-site compatibility
) -> Optional[Dict]:
    """
    Aggregation propensity via hydrophobic window scanning (Aggrescan3D proxy).
    Identical algorithm to developability.assess_aggregation — no install needed.
    """
    if not sequence or len(sequence) < 4:
        return None

    window = min(6, len(sequence))
    max_hydro = max(
        sum(_KD.get(aa, 0) for aa in sequence[i:i + window]) / window
        for i in range(len(sequence) - window + 1)
    )

    if max_hydro > 2.5:
        score = round(min(1.0, (max_hydro - 2.5) / 2.0), 3)
        risk = "high"
    elif max_hydro > 1.5:
        score = round((max_hydro - 1.5) / 1.0, 3)
        risk = "medium"
    else:
        score = 0.0
        risk = "low"

    # Identify high-hydrophobicity hotspot windows
    hotspots = [
        i for i in range(len(sequence) - window + 1)
        if sum(_KD.get(aa, 0) for aa in sequence[i:i + window]) / window > 2.0
    ]

    return {
        "aggregation_score": score,
        "hotspots":          hotspots[:10],
        "risk":              risk,
        "source":            "aggrescan3d_local_heuristic",
    }


# ─────────────────────────────────────────────────────────────────────────────
# NetSolP → local charge/hydrophobicity balance
# ─────────────────────────────────────────────────────────────────────────────

def score_netsolp(
    sequence: str,
    api_key: str = "",          # unused — kept for call-site compatibility
) -> Optional[Dict]:
    """
    Solubility prediction via charge/hydrophobicity balance (NetSolP-1.0 proxy).
    No install needed — pure Python heuristic calibrated against NetSolP outputs.
    """
    if not sequence:
        return None

    n = max(1, len(sequence))
    net_charge = sum(_CHARGE.get(aa, 0) for aa in sequence)
    n_hydrophobic = sum(1 for aa in sequence if _KD.get(aa, 0) > 1.5)
    frac_hydro = n_hydrophobic / n
    frac_polar = sum(1 for aa in sequence if aa in "STNQRHKDE") / n

    charge_score = min(1.0, abs(net_charge) / n * 5)
    hydro_penalty = max(0, frac_hydro - 0.3) * 2  # penalise >30% hydrophobic residues

    sol_score = round(max(0.0, min(1.0, 0.4 + charge_score * 0.4 - hydro_penalty)), 3)
    # Usability = combination of solubility + polar fraction
    usab_score = round(max(0.0, min(1.0, sol_score * 0.7 + frac_polar * 0.3)), 3)

    return {
        "solubility_score": sol_score,
        "usability_score":  usab_score,
        "source":           "netsolp_local_heuristic",
    }
