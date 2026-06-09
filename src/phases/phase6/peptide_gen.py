"""
Phase 6 — Peptide / mini-binder sequence generation.

Generation ladder (each tier falls through to the next if unavailable):
  1. RFdiffusion local     — backbone gen (set RFDIFFUSION_DIR to your clone)
     → ProteinMPNN local   — sequence design on backbone (torch + tools/ProteinMPNN)
  2. RFdiffusion local     — same tool, direct call (deduplication tier)
     → ProteinMPNN local   — sequence design on backbone
  3. ProteinMPNN local     — design directly on target PDB (no binder backbone)
  4. LLM-assisted          — pure sequence generation from interface context (always available)
"""
from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Hosted generation stubs (activated by API keys)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_boltzgen_then_mpnn(interface_ctx: Dict, n_designs: int = 50) -> List[str]:
    """
    Tier 1: Local RFdiffusion backbones → ProteinMPNN sequence design.
    Returns [] if RFdiffusion is not installed (set RFDIFFUSION_DIR env var).
    """
    try:
        from .neurosnap_boltzgen import run_boltzgen
        backbones = run_boltzgen(interface_ctx, n_designs=n_designs)
        if backbones:
            mpnn_seqs = _run_mpnn_on_sequences(backbones, interface_ctx)
            return mpnn_seqs if mpnn_seqs else backbones
        return []
    except Exception as exc:
        log.warning("[6.gen] RFdiffusion+MPNN failed: %s", exc)
        return []


def _generate_rfdifffusion_nim(interface_ctx: Dict, n_backbones: int = 50) -> List[str]:
    """
    Tier 2: Local RFdiffusion backbones → ProteinMPNN (direct path, same tool as tier 1).
    Kept as a separate tier so the ladder structure is preserved.
    """
    try:
        from .nim_rfdiffusion import run_rfdiffusion_nim
        backbones = run_rfdiffusion_nim(interface_ctx, n_backbones=n_backbones)
        if backbones:
            mpnn_seqs = _run_mpnn_on_sequences(backbones, interface_ctx)
            return mpnn_seqs if mpnn_seqs else backbones
        return []
    except Exception as exc:
        log.warning("[6.gen] RFdiffusion local failed: %s", exc)
        return []


def _generate_proteinmpnn_on_target(interface_ctx: Dict, n_sequences: int = 20) -> List[str]:
    """
    Tier 3: ProteinMPNN directly on target PDB (no binder backbone).
    Designs sequences that fit the target binding site.
    Requires tools/ProteinMPNN + torch (no API key needed).
    """
    try:
        from pathlib import Path
        from .proteinmpnn_runner import is_available, design_sequences
        if not is_available():
            return []
        # P2 stores a local file path in pdb_path (interface_analysis.py populates this key).
        pdb_path = interface_ctx.get("pdb_path", "")
        if not pdb_path:
            return []
        pdb_p = Path(pdb_path)
        if not pdb_p.exists():
            log.warning("[6.gen] ProteinMPNN: pdb_path not found: %s", pdb_path)
            return []
        sequences = design_sequences(pdb_p, n_sequences=n_sequences)
        log.info("[6.gen] ProteinMPNN-on-target: %d sequences", len(sequences))
        return sequences
    except Exception as exc:
        log.warning("[6.gen] ProteinMPNN-on-target failed: %s", exc)
        return []


def _run_mpnn_on_sequences(backbone_sequences: List[str], interface_ctx: Dict) -> List[str]:
    """
    Run ProteinMPNN to redesign sequences on top of backbone sequences.
    Since ProteinMPNN needs a PDB not raw sequences, we use the target PDB
    and design new sequences for it, biased toward the backbone length range.
    """
    try:
        from pathlib import Path
        from .proteinmpnn_runner import is_available, design_sequences
        if not is_available():
            return []
        pdb_path = interface_ctx.get("pdb_path", "")
        if not pdb_path:
            return backbone_sequences
        pdb_p = Path(pdb_path)
        if not pdb_p.exists():
            return backbone_sequences
        mpnn_seqs = design_sequences(pdb_p, n_sequences=len(backbone_sequences) * 2)
        return mpnn_seqs if mpnn_seqs else backbone_sequences
    except Exception as exc:
        log.debug("[6.gen] ProteinMPNN redesign failed: %s", exc)
        return backbone_sequences


# ─────────────────────────────────────────────────────────────────────────────
# LLM-assisted fallback generation
# ─────────────────────────────────────────────────────────────────────────────

_AA_SINGLE = "ACDEFGHIKLMNPQRSTVWY"

_STRATEGY_PROMPTS = {
    "antibody_epitope": (
        "Design linear peptides (12-20 aa) that mimic or block an antibody epitope "
        "on the extracellular domain. Use hydrophilic residues for surface exposure. "
        "Include at least one charged residue for solubility."
    ),
    "cyclic_peptide": (
        "Design cyclic peptides (8-16 aa) for intracellular targets. "
        "Cyclic for proteolytic stability. Include a Pro or Gly for turn induction. "
        "Balance hydrophobicity for cell penetration (logP 0-2)."
    ),
    "helical_mimetic": (
        "Design alpha-helical peptides (14-21 aa, i,i+4 heptad repeat) to mimic "
        "a helix-helix PPI interface. Place hydrophobic residues on one face "
        "(L, I, V, F at positions i, i+3/4, i+7) and charged on the other."
    ),
    "stapled_peptide": (
        "Design stapled peptides (14-21 aa) for disordered targets. "
        "Include two Cys or non-natural residues at i, i+4 for hydrocarbon stapling. "
        "Helical constraint improves proteolytic stability and cell penetration."
    ),
}


def _build_llm_generation_prompt(
    symbol: str,
    interface_ctx: Dict,
    n_sequences: int,
    known_sequences: List[str],
) -> str:
    strategy = interface_ctx.get("design_strategy", "cyclic_peptide")
    hotspots = interface_ctx.get("hotspots", [])
    length_range = interface_ctx.get("binder_length_range", (15, 30))
    cyclic = interface_ctx.get("cyclic_preferred", False)
    compartment = interface_ctx.get("compartment", "Unknown")
    chronos = interface_ctx.get("chronos_median", 0.0)

    strategy_hint = _STRATEGY_PROMPTS.get(strategy, _STRATEGY_PROMPTS["cyclic_peptide"])
    hotspot_hint = (
        f"Known hotspot residues (high-pathogenicity AlphaMissense): {hotspots}"
        if hotspots else "No hotspot data available."
    )
    seed_hint = (
        f"Reference peptides from ChEMBL: {known_sequences[:5]}"
        if known_sequences else "No reference peptides available."
    )

    return (
        f"You are an expert in peptide drug design.\n\n"
        f"Target: {symbol}\n"
        f"Cellular compartment: {compartment}\n"
        f"Chronos essentiality: {chronos:.2f} (negative = essential)\n"
        f"Design strategy: {strategy}\n"
        f"Length range: {length_range[0]}–{length_range[1]} amino acids\n"
        f"Cyclic preferred: {cyclic}\n"
        f"{hotspot_hint}\n"
        f"{seed_hint}\n\n"
        f"Strategy guidance: {strategy_hint}\n\n"
        f"Generate exactly {n_sequences} candidate peptide sequences using single-letter "
        f"amino acid codes. Each must:\n"
        f"  1. Bind {symbol} at its active site or interface\n"
        f"  2. Be {length_range[0]}–{length_range[1]} residues long\n"
        f"  3. Use only standard amino acids ({_AA_SINGLE})\n"
        f"  4. Be distinct from each other (Hamming distance ≥ 3)\n\n"
        f"Return ONLY a JSON array of strings: "
        f'[\"ACDEF...\", \"GHIKL...\", ...]'
    )


def generate_with_llm(
    symbol: str,
    interface_ctx: Dict,
    provider,
    n_sequences: int = 20,
    known_sequences: Optional[List[str]] = None,
) -> List[str]:
    """
    Generate peptide sequences via LLM with interface context.
    Returns list of single-letter AA sequences.
    """
    prompt = _build_llm_generation_prompt(
        symbol=symbol,
        interface_ctx=interface_ctx,
        n_sequences=n_sequences,
        known_sequences=known_sequences or [],
    )
    try:
        result = provider.complete(prompt, temperature=0.7, max_tokens=8000)
        text = result.text.strip()

        # Extract JSON array
        m = re.search(r"\[.*?\]", text, re.DOTALL)
        if m:
            import json
            sequences = json.loads(m.group(0))
            # Validate: keep only sequences of valid AAs
            valid = []
            min_len, max_len = interface_ctx.get("binder_length_range", (8, 60))
            for seq in sequences:
                if isinstance(seq, str) and all(aa in _AA_SINGLE for aa in seq):
                    if min_len <= len(seq) <= max_len:
                        valid.append(seq.upper())
            log.info("[6.gen] LLM generated %d valid sequences", len(valid))
            return valid
        else:
            # Try to extract sequences line by line
            sequences = []
            for line in text.split("\n"):
                line = line.strip().strip('"').strip("'").strip(",")
                if line and all(aa in _AA_SINGLE for aa in line) and 5 <= len(line) <= 100:
                    sequences.append(line.upper())
            log.info("[6.gen] LLM (line parse): %d sequences", len(sequences))
            return sequences[:n_sequences]

    except Exception as exc:
        log.warning("[6.gen] LLM generation failed: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# ChEMBL peptide reference lookup
# ─────────────────────────────────────────────────────────────────────────────

def fetch_known_peptides(symbol: str, max_peptides: int = 10) -> List[str]:
    """
    Query ChEMBL local DB for peptide-like compounds (MW 200-2000, pChEMBL≥6).
    Returns list of SMILES (may be cyclic peptides — used as reference, not AA seq).
    """
    try:
        import sqlite3
        from pathlib import Path
        from src.config import settings
        db_path = Path(settings.DB_CHEMBL) / "chembl_35.db"
        if not db_path.exists():
            # Try chembl_34.db
            db_path = next(Path(settings.DB_CHEMBL).glob("chembl_*.db"), None)
        if not db_path:
            return []
        conn = sqlite3.connect(str(db_path))
        cur = conn.execute("""
            SELECT DISTINCT cs.canonical_smiles
            FROM activities a
            JOIN assays ay ON a.assay_id = ay.assay_id
            JOIN target_dictionary td ON ay.tid = td.tid
            JOIN compound_structures cs ON a.molregno = cs.molregno
            JOIN compound_properties cp ON a.molregno = cp.molregno
            WHERE td.pref_name LIKE ?
              AND a.pchembl_value >= 6.0
              AND cp.mw_freebase BETWEEN 200 AND 2000
              AND cp.alogp < 3
            LIMIT ?
        """, (f"%{symbol}%", max_peptides))
        results = [row[0] for row in cur.fetchall() if row[0]]
        conn.close()
        return results
    except Exception as exc:
        log.debug("[6.gen] ChEMBL peptide lookup failed: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_peptides(
    symbol: str,
    interface_ctx: Dict,
    provider,
    n_sequences: int = 30,
) -> List[str]:
    """
    Generate peptide sequences for a target.
    Full generation ladder:
      1. RFdiffusion local → ProteinMPNN  (requires RFDIFFUSION_DIR + models)
      2. RFdiffusion local → ProteinMPNN  (same tool; second attempt with different params)
      3. ProteinMPNN directly on target PDB  (sequences filtered to binder_length_range)
      4. LLM-assisted (always available)
    """
    min_len, max_len = interface_ctx.get("binder_length_range", (8, 60))

    # Tier 1: RFdiffusion (via BoltzGen shim) → ProteinMPNN
    sequences = _generate_boltzgen_then_mpnn(interface_ctx, n_designs=n_sequences)
    if sequences:
        log.info("[6.gen] %s: Tier 1 (RFdiffusion+MPNN) produced %d sequences", symbol, len(sequences))

    # Tier 2: RFdiffusion directly → ProteinMPNN
    if not sequences:
        sequences = _generate_rfdifffusion_nim(interface_ctx, n_backbones=n_sequences)
        if sequences:
            log.info("[6.gen] %s: Tier 2 (RFdiffusion direct) produced %d sequences", symbol, len(sequences))

    # Tier 3: ProteinMPNN on target PDB (redesigns target chain — filter to binder length range)
    if not sequences:
        raw = _generate_proteinmpnn_on_target(interface_ctx, n_sequences=n_sequences * 4)
        sequences = [s for s in raw if min_len <= len(s) <= max_len]
        if sequences:
            log.info("[6.gen] %s: Tier 3 (ProteinMPNN-on-target) produced %d in-range sequences "
                     "(from %d total)", symbol, len(sequences), len(raw))
        elif raw:
            log.info("[6.gen] %s: Tier 3 (ProteinMPNN-on-target) produced %d sequences but all "
                     "outside length range %d-%d — falling to LLM", symbol, len(raw), min_len, max_len)

    # Tier 4: LLM fallback (always available)
    if not sequences:
        log.info("[6.gen] %s: Tier 4 (LLM fallback) — Tiers 1-3 unavailable or empty", symbol)
        known = fetch_known_peptides(symbol)
        sequences = generate_with_llm(
            symbol=symbol,
            interface_ctx=interface_ctx,
            provider=provider,
            n_sequences=n_sequences,
            known_sequences=known,
        )

    # Deduplicate and enforce length bounds
    seen: set[str] = set()
    unique = []
    for seq in sequences:
        if seq not in seen and min_len <= len(seq) <= max_len:
            seen.add(seq)
            unique.append(seq)

    log.info("[6.gen] %s: %d unique sequences in range [%d, %d]", symbol, len(unique), min_len, max_len)
    return unique
