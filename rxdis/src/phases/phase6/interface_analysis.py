"""
Phase 6 — Target interface analysis.

Extracts:
  - Surface-exposed residues from structure (B-factor proxy if AFDB)
  - Known hotspot residues from AlphaMissense pathogenic variants
  - Interface region for PPI targets (extracellular / disordered)
  - Pocket-adjacent residues from Phase 2 fpocket output

Used to guide peptide/mini-binder design in peptide_gen.py.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# Amino acid properties (single-letter)
_HYDROPHOBIC = set("VILMFYWC")
_CHARGED     = set("RKHDE")
_POLAR       = set("STNQ")


def extract_hotspots_from_variants(variants: Dict) -> List[str]:
    """
    Extract hotspot residue hints from Phase 2 AlphaMissense variant data.
    Returns list of residue strings like ['R175', 'G12', 'V600'].
    """
    hotspots = []
    # Phase 2 stores high-pathogenicity missense count but not individual residues.
    # When full variant data is available in evidence_trail, extract them.
    raw_variants = variants.get("raw_variants", [])
    for v in raw_variants:
        if v.get("am_pathogenicity", 0) >= 0.8:
            pos = v.get("position") or v.get("protein_pos")
            aa = v.get("ref_aa") or v.get("wild_type_aa", "")
            if pos and aa:
                hotspots.append(f"{aa}{pos}")
    return hotspots[:10]


def extract_interface_from_pocket(pockets: List[Dict]) -> Dict:
    """
    Extract approximate binding interface coordinates from fpocket output.
    Returns center-of-mass + suggested binder length range.
    """
    if not pockets:
        return {}
    best = pockets[0]
    cx = best.get("cx") or best.get("center_x")
    cy = best.get("cy") or best.get("center_y")
    cz = best.get("cz") or best.get("center_z")
    volume = best.get("volume", 500.0)

    # Estimate binder length from pocket volume
    # Small pocket (<400 Å³) → short peptide 8-15aa
    # Medium (400-800 Å³) → 15-30aa
    # Large (>800 Å³) → mini-binder 30-60aa
    if volume < 400:
        min_len, max_len = 8, 15
    elif volume < 800:
        min_len, max_len = 15, 30
    else:
        min_len, max_len = 30, 60

    return {
        "cx": cx, "cy": cy, "cz": cz,
        "volume": volume,
        "druggability": best.get("druggability", 0.5),
        "binder_length_range": (min_len, max_len),
    }


def classify_target_modality(p2: Dict) -> Dict:
    """
    Classify the target's structural context for biologic design.

    Returns:
      target_class: 'extracellular' | 'membrane' | 'intracellular' | 'disordered'
      design_strategy: 'antibody_epitope' | 'cyclic_peptide' | 'helical_mimetic' | 'stapled_peptide'
      cyclic_preferred: bool (intracellular = proteolytic instability concern)
      ppi_interface: bool (structured PPI vs groove binder)
    """
    localization = p2.get("localization", {})
    compartment = localization.get("compartment", "Unknown")
    is_membrane = localization.get("is_membrane", False)
    is_secreted = localization.get("is_secreted", False)
    is_extracellular = compartment in ("Extracellular", "Plasma membrane")

    structure = p2.get("structure", {})
    median_plddt = float(structure.get("median_plddt") or 0)
    is_disordered = median_plddt < 60

    tractability = p2.get("tractability", {})
    primary_modality = tractability.get("primary_modality", "SM")

    if is_disordered:
        target_class = "disordered"
        design_strategy = "stapled_peptide"
        cyclic_preferred = True
    elif is_extracellular or is_secreted:
        target_class = "extracellular"
        design_strategy = "antibody_epitope"
        cyclic_preferred = False
    elif is_membrane:
        target_class = "membrane"
        design_strategy = "cyclic_peptide"
        cyclic_preferred = True
    else:
        target_class = "intracellular"
        design_strategy = "cyclic_peptide" if primary_modality in ("PROTAC", "peptide") else "helical_mimetic"
        cyclic_preferred = True

    return {
        "target_class": target_class,
        "design_strategy": design_strategy,
        "cyclic_preferred": cyclic_preferred,
        "ppi_interface": target_class in ("extracellular", "disordered"),
        "compartment": compartment,
    }


def build_interface_context(symbol: str, p2: Dict) -> Dict:
    """
    Aggregate all interface information for peptide design.
    Returns a unified interface_context dict passed to peptide_gen.
    """
    modality_class = classify_target_modality(p2)
    pocket_info = extract_interface_from_pocket(p2.get("pockets", []))
    hotspots = extract_hotspots_from_variants(p2.get("variants", {}))

    # Infer interface type from essentiality data
    essentiality = p2.get("essentiality", {})
    chronos = float(essentiality.get("chronos_median") or 0)

    return {
        "symbol": symbol,
        "target_class": modality_class["target_class"],
        "design_strategy": modality_class["design_strategy"],
        "cyclic_preferred": modality_class["cyclic_preferred"],
        "ppi_interface": modality_class["ppi_interface"],
        "compartment": modality_class["compartment"],
        "pocket": pocket_info,
        "hotspots": hotspots,
        "chronos_median": chronos,
        "binder_length_range": pocket_info.get("binder_length_range", (15, 30)),
        # P2 stores a local file path in pdb_path (no remote URL is kept after download).
        "pdb_path": p2.get("structure", {}).get("pdb_path"),
        "plddt": float(p2.get("structure", {}).get("median_plddt") or 0),
    }
