"""
Phase 2.2 — Structure acquisition with routing fallthrough.

Routing order (PRD §2.2):
  1. PDB (RCSB / PDBe SIFTS, experimental)   → highest confidence, no pLDDT
  2. AlphaFold DB (instant, per-UniProt)     → pLDDT from B-factor column
  3. ESMFold via NVIDIA NIM (novel seqs)     → requires NIM_API_KEY
  4/5. AF Server AF3 / OmegaFold / Boltz-1   → out of scope here (logged as TODO)

median pLDDT < 70  → caller routes to 2.6 disordered subroutine.
Per-residue pLDDT is reduced to confident ("ordered") residue ranges so the 2.2
LLM gate and downstream pocket logic can restrict to folded domains.

No biopython dependency — PDB ATOM records are parsed by fixed-column slicing,
which is the canonical PDB format and avoids the optional Bio import.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
import numpy as np

from src.config import settings

log = logging.getLogger(__name__)

_AFDB_URL = "https://alphafold.ebi.ac.uk/files/AF-{acc}-F1-model_v{ver}.pdb"
_PDBE_BEST = "https://www.ebi.ac.uk/pdbe/api/mappings/best_structures/{acc}"
_RCSB_FILE = "https://files.rcsb.org/download/{pdb_id}.pdb"
_NIM_ESMFOLD = "https://health.api.nvidia.com/v1/biology/nvidia/esmfold"

_PLDDT_CONFIDENT = 70.0


def _cache_dir() -> Path:
    d = Path("output") / "structures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def acquire_structure(symbol: str, uniprot: Optional[str], sequence: str = "") -> Dict:
    """
    Run the routing fallthrough for one target.
    Returns:
      {source, uniprot, pdb_id, pdb_path, median_plddt, ordered_ranges,
       disordered_ranges, low_confidence, n_residues}
    """
    result = {
        "source": "none",
        "uniprot": uniprot,
        "pdb_id": None,
        "pdb_path": None,
        "median_plddt": None,
        "ordered_ranges": [],
        "disordered_ranges": [],
        "low_confidence": True,
        "n_residues": 0,
    }
    if not uniprot:
        log.warning("[2.2] %s: no UniProt, cannot fetch structure", symbol)
        return result

    # 1. Experimental PDB (preferred when available)
    pdb_id = _best_experimental_pdb(uniprot)
    if pdb_id:
        path = _download(_RCSB_FILE.format(pdb_id=pdb_id), _cache_dir() / f"{symbol}_{pdb_id}.pdb")
        if path:
            n_res = _count_residues(path)
            result.update({
                "source": "PDB", "pdb_id": pdb_id, "pdb_path": str(path),
                # experimental → treat as fully confident
                "median_plddt": 100.0, "low_confidence": False, "n_residues": n_res,
                "ordered_ranges": [f"1-{n_res}"] if n_res else [],
            })
            log.info("[2.2] %s: experimental PDB %s (%d res)", symbol, pdb_id, n_res)
            return result

    # 2. AlphaFold DB
    afdb = _fetch_afdb(uniprot, _cache_dir() / f"{symbol}_AF.pdb")
    if afdb:
        path, plddts = afdb
        median = float(np.median(plddts)) if plddts else 0.0
        ordered, disordered = _confident_ranges(plddts)
        result.update({
            "source": "AFDB", "pdb_path": str(path),
            "median_plddt": round(median, 1),
            "ordered_ranges": ordered, "disordered_ranges": disordered,
            "low_confidence": median < _PLDDT_CONFIDENT,
            "n_residues": len(plddts),
        })
        log.info("[2.2] %s: AFDB median pLDDT=%.1f (%d res, %d ordered segs)",
                 symbol, median, len(plddts), len(ordered))
        return result

    # 3. ESMFold via NIM (only for novel sequences not in AFDB)
    if sequence and settings.NIM_API_KEY:
        esm = _esmfold_nim(sequence, _cache_dir() / f"{symbol}_ESM.pdb")
        if esm:
            path, plddts = esm
            median = float(np.median(plddts)) if plddts else 0.0
            ordered, disordered = _confident_ranges(plddts)
            result.update({
                "source": "ESMFold", "pdb_path": str(path),
                "median_plddt": round(median, 1),
                "ordered_ranges": ordered, "disordered_ranges": disordered,
                "low_confidence": median < _PLDDT_CONFIDENT,
                "n_residues": len(plddts),
            })
            log.info("[2.2] %s: ESMFold median pLDDT=%.1f", symbol, median)
            return result

    log.warning("[2.2] %s: no structure from PDB/AFDB/ESMFold (AF3 fallback not implemented)", symbol)
    return result


# ── Source-specific fetchers ──────────────────────────────────────────────────

def _best_experimental_pdb(uniprot: str) -> Optional[str]:
    """Highest-coverage experimental PDB for a UniProt accession (PDBe SIFTS)."""
    try:
        resp = httpx.get(_PDBE_BEST.format(acc=uniprot), timeout=20)
        if resp.status_code != 200:
            return None
        entries = resp.json().get(uniprot, [])
        return entries[0]["pdb_id"].upper() if entries else None
    except Exception as exc:
        log.debug("[2.2] PDBe lookup failed for %s: %s", uniprot, exc)
        return None


def _fetch_afdb(uniprot: str, dest: Path) -> Optional[Tuple[Path, List[float]]]:
    for ver in (4, 3, 2):
        path = _download(_AFDB_URL.format(acc=uniprot, ver=ver), dest)
        if path:
            return path, _parse_ca_plddt(path)
    return None


def _esmfold_nim(sequence: str, dest: Path) -> Optional[Tuple[Path, List[float]]]:
    """Call NVIDIA NIM ESMFold. Sequence capped at 1024 aa (model limit)."""
    seq = sequence[:1024]
    headers = {"Authorization": f"Bearer {settings.NIM_API_KEY}",
               "Accept": "application/json"}
    try:
        resp = httpx.post(_NIM_ESMFOLD, headers=headers,
                          json={"sequence": seq}, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        # NIM returns PDB text in 'pdbs' (list) or 'pdb_string'
        pdb_text = ""
        if isinstance(data.get("pdbs"), list) and data["pdbs"]:
            pdb_text = data["pdbs"][0]
        else:
            pdb_text = data.get("pdb_string", "")
        if not pdb_text:
            return None
        dest.write_text(pdb_text)
        return dest, _parse_ca_plddt(dest)
    except Exception as exc:
        log.warning("[2.2] ESMFold NIM failed: %s", exc)
        return None


# ── PDB text parsing (column-fixed, no biopython) ─────────────────────────────

def _parse_ca_plddt(path: Path) -> List[float]:
    """Per-residue pLDDT = B-factor of each CA atom (AFDB/ESMFold convention)."""
    plddts: List[float] = []
    try:
        with path.open() as fh:
            for line in fh:
                if line.startswith("ATOM") and line[12:16].strip() == "CA":
                    try:
                        plddts.append(float(line[60:66]))
                    except ValueError:
                        continue
    except Exception as exc:
        log.warning("[2.2] pLDDT parse failed for %s: %s", path, exc)
    return plddts


def _count_residues(path: Path) -> int:
    seen = set()
    try:
        with path.open() as fh:
            for line in fh:
                if line.startswith("ATOM") and line[12:16].strip() == "CA":
                    seen.add((line[21], line[22:26].strip()))
    except Exception:
        return 0
    return len(seen)


def _confident_ranges(plddts: List[float], min_len: int = 5) -> Tuple[List[str], List[str]]:
    """Contiguous residue ranges above / below the confidence cutoff."""
    if not plddts:
        return [], []
    ordered, disordered = [], []
    start, conf = 1, plddts[0] >= _PLDDT_CONFIDENT
    for i, p in enumerate(plddts[1:], start=2):
        is_conf = p >= _PLDDT_CONFIDENT
        if is_conf != conf:
            seg = f"{start}-{i - 1}"
            (ordered if conf else disordered).append((seg, i - start))
            start, conf = i, is_conf
    seg = f"{start}-{len(plddts)}"
    (ordered if conf else disordered).append((seg, len(plddts) - start + 1))
    # Keep only segments of meaningful length
    ordered = [s for s, ln in ordered if ln >= min_len]
    disordered = [s for s, ln in disordered if ln >= min_len]
    return ordered, disordered


def _download(url: str, dest: Path, retries: int = 2) -> Optional[Path]:
    for attempt in range(retries):
        try:
            resp = httpx.get(url, timeout=60, follow_redirects=True)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return dest
        except Exception as exc:
            log.debug("[2.2] download %s failed (%d/%d): %s", url, attempt + 1, retries, exc)
    return None
