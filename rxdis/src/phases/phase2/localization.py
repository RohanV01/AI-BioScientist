"""
Phase 2.6 (partial) — Subcellular localization & membrane/secreted classification.

Determines whether a target is intracellular, transmembrane (with an
extracellular domain), or secreted/extracellular. This is the single most
important input to modality routing (Phase 3):
  - extracellular / secreted          → antibody, peptide
  - transmembrane with ECD            → antibody (against ECD)
  - intracellular                     → small molecule, PROTAC, oligo

Source: HPA per-gene record (Protein class, Subcellular location, Secretome).
UniProt keywords (from uniprot.py) provide a cross-check / fallback for genes
absent from HPA.

Also surfaces a coarse disorder hint used by the 2.6 disordered subroutine,
combined in the runner with structure pLDDT.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

from .hpa import get_hpa

log = logging.getLogger(__name__)

_MEMBRANE_TOKENS = ("plasma membrane", "cell membrane")
_SECRETED_TOKENS = ("secreted", "extracellular")


def classify_localization(symbol: str, ensembl_id: str,
                          uniprot_meta: Optional[Dict] = None) -> Dict:
    """
    Returns:
      {compartment, is_membrane, is_secreted, is_intracellular,
       has_ecd, subcellular, source}
    compartment ∈ {"intracellular","membrane","secreted","unknown"}
    """
    hpa = get_hpa(ensembl_id)
    if hpa:
        return _from_hpa(symbol, hpa)
    if uniprot_meta:
        return _from_uniprot(symbol, uniprot_meta)
    log.warning("[2.6] %s: no localization source (HPA/UniProt)", symbol)
    return {"compartment": "unknown", "is_membrane": False, "is_secreted": False,
            "is_intracellular": True, "has_ecd": False, "subcellular": "", "source": "none"}


def _from_hpa(symbol: str, hpa: Dict[str, str]) -> Dict:
    protein_class = hpa.get("Protein class", "").lower()
    subloc = (hpa.get("Subcellular main location", "")
              or hpa.get("Subcellular location", "")).lower()
    secretome = hpa.get("Secretome location", "").strip()

    is_membrane = (
        "membrane protein" in protein_class
        or any(tok in subloc for tok in _MEMBRANE_TOKENS)
    )
    is_secreted = bool(secretome) or "secreted protein" in protein_class

    if is_secreted and not is_membrane:
        compartment = "secreted"
    elif is_membrane:
        compartment = "membrane"
    else:
        compartment = "intracellular"

    # Cell-surface / membrane receptors and secreted proteins are antibody-amenable.
    has_ecd = is_membrane or is_secreted

    return {
        "compartment": compartment,
        "is_membrane": is_membrane,
        "is_secreted": is_secreted,
        "is_intracellular": compartment == "intracellular",
        "has_ecd": has_ecd,
        "subcellular": hpa.get("Subcellular main location", "") or hpa.get("Subcellular location", ""),
        "source": "hpa",
    }


def _from_uniprot(symbol: str, meta: Dict) -> Dict:
    kws = [k.lower() for k in meta.get("keywords", [])]
    is_membrane = any("membrane" in k or "transmembrane" in k for k in kws)
    is_secreted = any("secreted" in k for k in kws)
    if is_secreted and not is_membrane:
        compartment = "secreted"
    elif is_membrane:
        compartment = "membrane"
    else:
        compartment = "intracellular"
    return {
        "compartment": compartment,
        "is_membrane": is_membrane,
        "is_secreted": is_secreted,
        "is_intracellular": compartment == "intracellular",
        "has_ecd": is_membrane or is_secreted,
        "subcellular": ", ".join(meta.get("keywords", [])[:5]),
        "source": "uniprot",
    }
