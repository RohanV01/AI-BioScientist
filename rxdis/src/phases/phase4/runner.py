"""
Phase 4 runner — Drug Repurposing.

For every target routed to the P4_repurpose branch by Phase 3, we:

  4.1  Tier 1 — known-mechanism drugs (ChEMBL drug_mechanism)
       Fast: 5–100 compounds, docked at exhaustiveness=8.
       These are the highest-confidence repurposing candidates because
       a mechanism of action against the target is already confirmed.

  4.2  Tier 2 — virtual screening of the approved drug library
       Dock ChEMBL max_phase≥4 compounds (~3–5K) against the pocket
       at exhaustiveness=4 (speed/accuracy trade-off justified in docking.py).
       Compounds from Tier 1 are excluded to avoid double-counting.

  4.3  PrimeKG enrichment
       Each candidate receives a KG score (0/0.5/1.0) from PrimeKG
       drug_protein edges, adding an orthogonal curated-database signal.

  4.4  Triangulation scoring
       repurposing_score = 0.40*docking + 0.35*clinical + 0.25*KG
       Filter: keep top candidates_per_target_max with score ≥ 0.20.
       Strict gate (score ≥ 0.30) marks "passed"; borderline kept but flagged.

  4.5  LLM narrative gate
       For top-N passed candidates: 4-sentence repurposing rationale
       (drug, target, mechanism, clinical context).

Output contract (phase_results.output_json for phase 4):
  {
    "repurposing": {
      "KRAS": [
        {
          "drug_name": "SOTORASIB",
          "chembl_id": "...",
          "smiles": "...",
          "vina_score": -11.2,
          "vina_norm": 0.93,
          "clinical_score": 1.0,
          "kg_score": 1.0,
          "repurposing_score": 0.97,
          "passed": true,
          "rank": 1,
          "mechanism_of_action": "GTPase KRas inhibitor",
          "narrative": "..."
        }, ...
      ]
    },
    "n_targets_screened": 5,
    "n_candidates_total": 18,
    "wall_time_s": 1820.4,
  }
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config.run_config import RunConfig
from src.db import run_state

from .chembl_query import fingerprint_filter, get_approved_library, get_family_reference_smiles, get_target_drugs
from .docking import check_structure_quality, detect_covalent_target, dock_library, prepare_receptor_pdbqt
from .lincs_query import build_disease_signature, get_lincs_score
from .primekg_query import get_kg_score
from .scoring import calibrate_and_rescore, filter_candidates, rank_candidates

log = logging.getLogger(__name__)

# Hard cap to keep runtimes predictable
_MAX_LIBRARY_SCREEN = int(os.environ.get("P4_MAX_LIBRARY", "3000"))
_N_WORKERS = int(os.environ.get("P4_WORKERS", "4"))


def run_phase4(
    run_id: str,
    config: RunConfig,
    db,
    phase2_output: Dict,
    phase3_output: Dict,
    phase1_output: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Execute Phase 4. Returns the standardised output JSON and writes to DB."""
    from src.phases.base_runner import PhaseGuard
    t_start = time.monotonic()
    with PhaseGuard(db, run_id, phase=4, config=config) as guard:
        guard.check_budget()
        guard.validate_input(phase2_output, ["validated_targets"], source_phase=2)
        guard.validate_input(phase3_output, ["routing"], source_phase=3)
        return _run_phase4_body(
            run_id=run_id, config=config, db=db,
            phase1_output=phase1_output,
            phase2_output=phase2_output,
            phase3_output=phase3_output,
            t_start=t_start,
        )


def _run_phase4_body(
    run_id: str,
    config: RunConfig,
    db,
    phase1_output: Optional[Dict],
    phase2_output: Dict,
    phase3_output: Dict,
    t_start: float,
) -> Dict[str, Any]:
    provider = _make_provider(config)

    # H3: Build disease signature — up from P1 ranked targets, dn from P2 essentiality
    # (falls back to cancer TSG list when neither source has chronos data)
    ranked_targets = (phase1_output or {}).get("ranked_targets", [])
    validated_targets_for_sig = phase2_output.get("validated_targets", [])
    disease_up, disease_dn = build_disease_signature(
        ranked_targets,
        validated_targets=validated_targets_for_sig,
        indication_type=config.indication_type,
        disease_efo_id=config.disease_efo_id,
    )
    log.info("[4] Disease signature: %d up / %d dn genes for LINCS", len(disease_up), len(disease_dn))

    # Build a lookup: symbol → Phase 2 target record
    p2_by_symbol: Dict[str, Dict] = {
        t["symbol"]: t
        for t in phase2_output.get("validated_targets", [])
    }

    # Identify targets routed to P4
    repurpose_targets = [
        r for r in phase3_output.get("routing", [])
        if "P4_repurpose" in r.get("branches", [])
    ]
    log.info("[Phase 4] Repurposing %d targets", len(repurpose_targets))

    if not repurpose_targets:
        output = _empty_output(phase3_output, t_start)
        run_state.mark_phase_completed(db, run_id, phase=4, output=output)
        return output

    # Pre-load approved library once for all targets
    library_df = get_approved_library(min_phase=4, max_compounds=_MAX_LIBRARY_SCREEN)
    library_records = library_df.to_dict("records") if not library_df.empty else []

    repurposing_results: Dict[str, List[Dict]] = {}
    total_candidates = 0

    for routing in repurpose_targets:
        symbol: str = routing["symbol"]
        p2: Dict = p2_by_symbol.get(symbol, {})
        t0 = time.monotonic()
        log.info("[4] → %s", symbol)

        try:
            hits = _repurpose_one(
                symbol=symbol,
                p2=p2,
                config=config,
                provider=provider,
                library_records=library_records,
                disease_up=disease_up,
                disease_dn=disease_dn,
                db=db,
                run_id=run_id,
            )
        except Exception as exc:
            log.error("[4] %s failed: %s", symbol, exc, exc_info=True)
            hits = []

        repurposing_results[symbol] = hits
        total_candidates += len(hits)

        _persist_candidates(db, run_id, symbol, hits)
        log.info("[4] %s: %d candidates (%.1fs)", symbol, len(hits), time.monotonic() - t0)

    wall_time = round(time.monotonic() - t_start, 1)
    output = {
        "repurposing": repurposing_results,
        "n_targets_screened": len(repurpose_targets),
        "n_candidates_total": total_candidates,
        "wall_time_s": wall_time,
    }
    run_state.mark_phase_completed(db, run_id, phase=4, output=output)
    run_state.log_compute(
        db, run_id=run_id, phase=4, step="phase4_complete",
        service="local", wall_time_s=wall_time,
    )
    log.info("[Phase 4] Complete: %d candidates across %d targets (%.1fs)",
             total_candidates, len(repurpose_targets), wall_time)
    return output


# ─────────────────────────────────────────────────────────────────────────────
# Per-target repurposing
# ─────────────────────────────────────────────────────────────────────────────

def _repurpose_one(
    *,
    symbol: str,
    p2: Dict,
    config: RunConfig,
    provider,
    library_records: List[Dict],
    disease_up: List[str],
    disease_dn: List[str],
    db,
    run_id: str,
) -> List[Dict]:
    """Run the full repurposing pipeline for a single target."""

    uniprot_id: Optional[str] = p2.get("structure", {}).get("uniprot")
    # P2 stores a local file path in pdb_path (not a URL); prepare_receptor_pdbqt accepts both.
    pdb_url: Optional[str] = p2.get("structure", {}).get("pdb_path") or None
    pockets: List[Dict] = p2.get("pockets", [])
    best_pocket: Optional[Dict] = pockets[0] if pockets else None

    # Determine if docking is feasible
    pocket_ready = best_pocket and best_pocket.get("cx") is not None
    docking_available = False
    receptor_pdbqt: Optional[Path] = None
    tmp_dir = None

    # ── 4.1 Tier 1: known-mechanism drugs ─────────────────────────────────
    tier1 = get_target_drugs(symbol, uniprot_id=uniprot_id)
    tier1_names = {d["drug_name"] for d in tier1}
    log.info("[4.1] %s: %d Tier-1 drugs", symbol, len(tier1))

    # B4: detect covalent target — flag all candidates later
    p2_variants = p2.get("variants", {})
    covalent_info = detect_covalent_target(tier1, variants=p2_variants)
    if covalent_info["is_covalent"]:
        log.warning("[4.cov] %s: %s", symbol, covalent_info["covalent_note"][:100])

    # ── 4.2 Tier 2: approved-library virtual screening ────────────────────
    # Deduplicate against Tier 1 (same drug name, case-insensitive)
    tier2_raw = [
        rec for rec in library_records
        if rec.get("drug_name", "").upper() not in tier1_names
        and rec.get("smiles")
    ]
    # H1 fix: fingerprint pre-filter — keeps compounds similar to Tier-1 known
    # binders (Tanimoto ≥ 0.15) + 20% diversity sample. Cuts 3K → ~800 compounds.
    # B6 fix: for Tdark targets (empty Tier-1), use protein-family drugs as reference
    tier1_smiles = [d["smiles"] for d in tier1 if d.get("smiles")]
    if not tier1_smiles:
        tier1_smiles = get_family_reference_smiles(uniprot_id, symbol)
        if tier1_smiles:
            log.info("[4.2] %s: Tdark — using %d protein-family SMILES as pre-filter reference",
                     symbol, len(tier1_smiles))
    tier2 = fingerprint_filter(tier2_raw, reference_smiles=tier1_smiles, threshold=0.15, max_compounds=800)
    log.info("[4.2] %s: %d → %d Tier-2 compounds after pre-filter", symbol, len(tier2_raw), len(tier2))

    all_candidates = tier1 + tier2

    # ── Receptor preparation ──────────────────────────────────────────────
    # H4 fix: skip docking if structure is low-confidence (pLDDT < 70)
    plddt = float(p2.get("structure", {}).get("median_plddt") or 100.0)
    if not check_structure_quality(plddt):
        log.warning(
            "[4] %s: pLDDT=%.1f < 70 — structure unreliable, docking skipped (clinical+KG only)",
            symbol, plddt,
        )
        pocket_ready = False  # prevents docking block below

    if pocket_ready and pdb_url and all_candidates:
        try:
            tmp_dir = tempfile.mkdtemp(prefix=f"rxdis_p4_{symbol}_")
            tmp_path = Path(tmp_dir)
            receptor_pdbqt = prepare_receptor_pdbqt(pdb_url, tmp_path)
            if receptor_pdbqt:
                docking_available = True
                log.info("[4] %s: receptor PDBQT ready (%d bytes)",
                         symbol, receptor_pdbqt.stat().st_size)
            else:
                log.warning("[4] %s: receptor prep failed — docking skipped", symbol)
        except Exception as exc:
            log.warning("[4] %s: receptor prep error: %s", symbol, exc)

    # ── 4.3 Docking ───────────────────────────────────────────────────────
    if docking_available and receptor_pdbqt and best_pocket:
        # Tier 1 at high exhaustiveness (known drugs — fewer, more accurate)
        if tier1:
            tier1_dir = Path(tmp_dir) / "tier1"
            tier1_dir.mkdir(parents=True, exist_ok=True)
            log.info("[4.dock] %s: docking %d Tier-1 drugs (exhaustiveness=8)", symbol, len(tier1))
            tier1 = dock_library(
                candidates=tier1,
                receptor_pdbqt=receptor_pdbqt,
                pocket=best_pocket,
                work_dir=tier1_dir,
                exhaustiveness=8,
                n_workers=_N_WORKERS,
            )

        # Tier 2 at reduced exhaustiveness (bulk screening)
        if tier2:
            tier2_dir = Path(tmp_dir) / "tier2"
            tier2_dir.mkdir(parents=True, exist_ok=True)
            log.info("[4.dock] %s: docking %d Tier-2 drugs (exhaustiveness=4)", symbol, len(tier2))
            tier2 = dock_library(
                candidates=tier2,
                receptor_pdbqt=receptor_pdbqt,
                pocket=best_pocket,
                work_dir=tier2_dir,
                exhaustiveness=4,
                n_workers=_N_WORKERS,
            )

        all_candidates = tier1 + tier2

        # ── DiffDock local rescoring (optional) ──────────────────────────
        # Rescores top-200 Vina hits via local DiffDock for higher-accuracy pose ranking.
        # Install: git clone https://github.com/gcorso/DiffDock ~/tools/DiffDock
        if all_candidates:
            try:
                from .diffdock_nim import rescore_top_candidates
                all_candidates = rescore_top_candidates(
                    candidates=all_candidates,
                    receptor_pdbqt=receptor_pdbqt,
                    pocket=best_pocket,
                    top_n=200,
                    api_key=nim_key,
                )
                log.info("[4.nim] %s: DiffDock NIM rescoring complete", symbol)
            except (ImportError, NameError):
                log.debug("[4.nim] diffdock_nim module not yet available")
            except Exception as exc:
                log.warning("[4.nim] DiffDock NIM rescoring failed: %s", exc)
    else:
        # No docking — mark all vina_score as None
        for c in all_candidates:
            c.setdefault("vina_score", None)

    # ── 4.3 PrimeKG + LINCS enrichment ───────────────────────────────────
    lincs_available = bool(disease_up or disease_dn)
    for c in all_candidates:
        c["kg_score"] = get_kg_score(symbol, c.get("drug_name", ""))
        c["lincs_score"] = (
            get_lincs_score(c.get("drug_name", ""), symbol, disease_up, disease_dn)
            if lincs_available else 0.0
        )

    # ── 4.4 Two-pass scoring: calibrate Vina ceiling then score (B2 fix) ──
    all_candidates = calibrate_and_rescore(
        all_candidates,
        docking_available=docking_available,
        lincs_available=lincs_available,
    )
    if all_candidates:
        log.info("[4.score] %s: Vina ceiling calibrated to %.2f kcal/mol",
                 symbol, all_candidates[0].get("vina_ceiling_used", -12))

    # Filter and rank
    filtered = filter_candidates(all_candidates, vina_threshold=-7.0, min_score=0.20)
    ranked = rank_candidates(filtered)
    top_n = ranked[: config.candidates_per_target_max]

    # Relax threshold if no candidates pass strict gate
    if not any(c.get("passed") for c in top_n) and all_candidates:
        log.warning("[4] %s: no candidates pass strict threshold — relaxing to -7.0 / 0.15", symbol)
        filtered2 = filter_candidates(all_candidates, vina_threshold=-7.0, min_score=0.15)
        top_n = rank_candidates(filtered2)[: config.candidates_per_target_max]

    # B4: stamp covalent flag on every candidate
    for c in top_n:
        c["is_covalent_target"] = covalent_info["is_covalent"]
        c["covalent_note"] = covalent_info.get("covalent_note", "")

    # ── 4.5 LLM narrative gate ────────────────────────────────────────────
    for candidate in top_n:
        if candidate.get("passed"):
            try:
                candidate["narrative"] = _gate_narrative(
                    provider=provider,
                    db=db,
                    run_id=run_id,
                    symbol=symbol,
                    candidate=candidate,
                )
            except Exception as exc:
                log.debug("[4.5] Narrative gate skipped for %s/%s: %s",
                          symbol, candidate.get("drug_name"), exc)
                candidate["narrative"] = ""
        else:
            candidate["narrative"] = ""

    # Cleanup temp dir
    if tmp_dir:
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    return top_n


# ─────────────────────────────────────────────────────────────────────────────
# LLM gate
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> Optional[Dict]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _gate_narrative(
    *,
    provider,
    db,
    run_id: str,
    symbol: str,
    candidate: Dict,
) -> str:
    """
    LLM gate 4.5 — generate a 4-sentence repurposing case for the candidate.
    Returns the narrative string.
    """
    drug = candidate.get("drug_name", "")
    moa = candidate.get("mechanism_of_action", "unknown MOA")
    vina = candidate.get("vina_score")
    vina_str = f"{vina:.1f} kcal/mol" if vina else "docking unavailable"
    max_phase = candidate.get("max_phase", 0)
    clinical_str = f"Phase {int(max_phase)}" if max_phase else "preclinical"
    kg = candidate.get("kg_score", 0.0)

    prompt = (
        f"You are a drug discovery expert writing a concise repurposing rationale.\n\n"
        f"Target: {symbol}\n"
        f"Drug: {drug}\n"
        f"Known MOA: {moa}\n"
        f"Clinical stage: {clinical_str}\n"
        f"Docking score: {vina_str}\n"
        f"PrimeKG KG score: {kg:.1f}\n"
        f"Repurposing score: {candidate.get('repurposing_score', 0):.2f}\n\n"
        f"Write exactly 4 sentences covering: (1) why this drug might work on {symbol}, "
        f"(2) the structural/mechanistic basis, (3) the clinical evidence, "
        f"(4) key risk or caveat.\n\n"
        f'Return ONLY: {{"narrative": "sentence1. sentence2. sentence3. sentence4."}}'
    )

    result = provider.complete(prompt, temperature=0.2, max_tokens=300)
    parsed = _extract_json(result.text)
    if parsed and "narrative" in parsed:
        narrative = str(parsed["narrative"])
    else:
        # Fallback: strip JSON artifacts
        narrative = re.sub(r'[{}"\[\]]', "", result.text).strip()[:400]

    run_state.log_decision(
        db,
        run_id=run_id,
        phase=4,
        gate=f"4.5_narrative_{symbol}_{drug}",
        provider=provider.name,
        model=getattr(provider, "model", "unknown"),
        prompt=prompt,
        raw_response=result.text,
        decision_json={"narrative": narrative},
    )
    return narrative


# ─────────────────────────────────────────────────────────────────────────────
# DB persistence
# ─────────────────────────────────────────────────────────────────────────────

def _persist_candidates(db, run_id: str, symbol: str, candidates: List[Dict]) -> None:
    for c in candidates:
        try:
            run_state.insert_candidate(
                db,
                run_id=run_id,
                symbol=symbol,
                phase=4,
                kind="repurposing",
                candidate_id=c.get("chembl_id") or c.get("drug_name", ""),
                name=c.get("drug_name", ""),
                smiles=c.get("smiles", ""),
                score=c.get("repurposing_score", 0.0),
                rank=c.get("rank", 0),
                passed=c.get("passed", False),
                evidence={
                    "vina_score": c.get("vina_score"),
                    "vina_norm": c.get("vina_norm"),
                    "clinical_score": c.get("clinical_score"),
                    "kg_score": c.get("kg_score"),
                    "max_phase": c.get("max_phase"),
                    "mechanism_of_action": c.get("mechanism_of_action", ""),
                    "weights_used": c.get("weights_used", {}),
                    "narrative": c.get("narrative", ""),
                    "source": c.get("source", ""),
                    "borderline": c.get("borderline", False),
                },
            )
        except Exception as exc:
            log.warning("[4] DB persist failed for %s/%s: %s",
                        symbol, c.get("drug_name"), exc)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_provider(config: RunConfig):
    from src.llm.factory import make_provider
    return make_provider(config.llm)


def _empty_output(phase3_output: Dict, t_start: float) -> Dict:
    return {
        "repurposing": {},
        "n_targets_screened": 0,
        "n_candidates_total": 0,
        "note": "No targets routed to P4_repurpose branch",
        "wall_time_s": round(time.monotonic() - t_start, 1),
    }
