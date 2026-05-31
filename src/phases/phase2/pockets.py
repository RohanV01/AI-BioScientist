"""
Phase 2.3 — Pocket detection & druggability.

Full PRD path: fpocket → PockDrug-Server → CASTp cross-check → cryptic (OpenMM).
This environment has neither fpocket nor OpenMM compiled, so the module:

  1. runs fpocket when it IS available (shutil.which) and parses its
     Drug Score per pocket from the `*_info.txt` output, then
  2. falls back to an OT-tractability-derived druggability estimate carried
     from Phase 1 (`tractability_max`), explicitly flagging that physical
     pocket detection was skipped (`detection="tractability_proxy"`).

Either way it returns a uniform pocket list so downstream scoring/modality logic
is identical. PRD rule: max druggability < 0.5 AND no cryptic → disable SM branch.
"""
from __future__ import annotations
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_DRUGGABLE_CUTOFF = 0.5


def detect_pockets(symbol: str, pdb_path: Optional[str], tractability_max: float) -> Dict:
    """
    Returns:
      {pockets: [{id, druggability, volume, strategy}],
       max_druggability, sm_branch_enabled, detection}
    """
    if pdb_path and shutil.which("fpocket"):
        pockets = _run_fpocket(symbol, pdb_path)
        if pockets:
            max_drug = max(p["druggability"] for p in pockets)
            return {
                "pockets": pockets,
                "max_druggability": round(max_drug, 3),
                "sm_branch_enabled": max_drug >= _DRUGGABLE_CUTOFF,
                "detection": "fpocket",
            }

    # Fallback: derive a single nominal pocket from OT tractability.
    # tractability_max already encodes "High-Quality Pocket"(0.55)/"Structure with
    # Ligand"(0.65)/"Approved Drug"(1.0) tiers from Phase 1 — a reasonable proxy.
    drug = round(float(tractability_max), 3)
    pockets = [{
        "id": "P1",
        "druggability": drug,
        "volume": None,
        "strategy": "orthosteric" if drug >= _DRUGGABLE_CUTOFF else "undruggable",
    }] if drug > 0 else []
    return {
        "pockets": pockets,
        "max_druggability": drug,
        "sm_branch_enabled": drug >= _DRUGGABLE_CUTOFF,
        "detection": "tractability_proxy",
    }


def _run_fpocket(symbol: str, pdb_path: str) -> List[Dict]:
    """Run fpocket and parse the Drug Score from each pocket's info block."""
    try:
        work = Path(tempfile.mkdtemp(prefix=f"fpocket_{symbol}_"))
        target = work / Path(pdb_path).name
        target.write_bytes(Path(pdb_path).read_bytes())
        subprocess.run(["fpocket", "-f", str(target)], cwd=work,
                       capture_output=True, timeout=600, check=True)
        info = work / f"{target.stem}_out" / f"{target.stem}_info.txt"
        if not info.exists():
            return []
        return _parse_fpocket_info(info.read_text())
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("[2.3] fpocket failed for %s: %s", symbol, exc)
        return []


def _parse_fpocket_info(text: str) -> List[Dict]:
    """Parse fpocket `_info.txt`: blocks of 'Pocket N :' with metric lines."""
    pockets: List[Dict] = []
    current: Optional[Dict] = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("pocket"):
            if current:
                pockets.append(current)
            current = {"id": f"P{stripped.split()[1]}", "druggability": 0.0,
                       "volume": None, "strategy": "orthosteric"}
        elif current is not None and ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip().lower()
            val = val.strip()
            try:
                if "drug" in key and "score" in key:   # "Drug Score" / "Druggability Score"
                    current["druggability"] = round(float(val), 3)
                elif key == "volume":                  # exact — not "Volume score"
                    current["volume"] = round(float(val), 1)
            except ValueError:
                pass
    if current:
        pockets.append(current)
    for p in pockets:
        if p["druggability"] < _DRUGGABLE_CUTOFF:
            p["strategy"] = "allosteric" if p["druggability"] > 0.2 else "undruggable"
    return pockets
