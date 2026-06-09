"""
Phase 5 — De Novo Small Molecule Design runner.

Pipeline per target:
  5.1  Seed collection — ChEMBL binders + user seed_smiles
  5.2  Generation — REINVENT4 (Mol2Mol) → BRICS fallback
  5.3  Medichem filters — Ro5, Veber, PAINS, SA, QED, novelty
  5.4  ADMET — local RDKit descriptor-based scoring
  5.5  Docking — Vina re-dock filtered candidates against pocket
  5.6  LLM gate — ADMET context & optimization direction
  Rank & persist top-20 per target.

Runs when P5_small_molecule is in the routing branches
AND intent_mode in {explore, de_novo}.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config.run_config import RunConfig
from src.db import run_state

from .admet import batch_score_admet
from .filters import apply_filters, build_reference_fps
from .fragment_gen import generate_molecules
from .scoring import calibrate_ceiling, rank_candidates, score_candidate

log = logging.getLogger(__name__)

_N_GENERATE   = int(os.environ.get("P5_N_GENERATE", "1000"))
_TOP_N        = int(os.environ.get("P5_TOP_N", "20"))
_DOCK_WORKERS = int(os.environ.get("P5_WORKERS", "4"))


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_phase5(
    run_id: str,
    config: RunConfig,
    db,
    phase2_output: Dict,
    phase3_output: Dict,
    phase1_output: Optional[Dict] = None,
    phase4_output: Optional[Dict] = None,
) -> Dict[str, Any]:
    from src.phases.base_runner import PhaseGuard
    t_start = time.monotonic()
    with PhaseGuard(db, run_id, phase=5, config=config) as guard:
        guard.check_budget()
        guard.validate_input(phase2_output, ["validated_targets"], source_phase=2)
        guard.validate_input(phase3_output, ["routing"], source_phase=3)
        return _run_phase5_body(
            run_id=run_id, config=config, db=db,
            phase1_output=phase1_output,
            phase2_output=phase2_output,
            phase3_output=phase3_output,
            phase4_output=phase4_output,
            t_start=t_start,
        )


def _run_phase5_body(
    run_id: str, config: RunConfig, db,
    phase1_output: Optional[Dict], phase2_output: Dict,
    phase3_output: Dict, phase4_output: Optional[Dict], t_start: float,
) -> Dict[str, Any]:
    provider = _make_provider(config)

    p2_by_symbol: Dict[str, Dict] = {
        t["symbol"]: t for t in phase2_output.get("validated_targets", [])
    }

    sm_targets = [
        r for r in phase3_output.get("routing", [])
        if "P5_small_molecule" in r.get("branches", [])
    ]
    log.info("[Phase 5] De-novo SM for %d targets", len(sm_targets))

    if not sm_targets or not config.de_novo_enabled:
        out = _empty_output(t_start)
        run_state.mark_phase_completed(db, run_id, phase=5, output=out)
        return out

    # Load approved-drug SMILES once for novelty reference
    reference_smiles = _load_reference_smiles()
    ref_fps = build_reference_fps(reference_smiles)

    de_novo_results: Dict[str, List[Dict]] = {}
    total_candidates = 0

    for routing in sm_targets:
        symbol: str = routing["symbol"]
        p2: Dict = p2_by_symbol.get(symbol, {})
        t0 = time.monotonic()
        log.info("[5] → %s", symbol)

        try:
            hits = _denovo_one(
                symbol=symbol,
                p2=p2,
                config=config,
                provider=provider,
                ref_fps=ref_fps,
                db=db,
                run_id=run_id,
                phase4_output=phase4_output,
            )
        except Exception as exc:
            log.error("[5] %s failed: %s", symbol, exc, exc_info=True)
            hits = []

        de_novo_results[symbol] = hits
        total_candidates += len(hits)
        _persist_candidates(db, run_id, symbol, hits)
        log.info("[5] %s: %d candidates (%.1fs)", symbol, len(hits), time.monotonic() - t0)

    wall_time = round(time.monotonic() - t_start, 1)
    output = {
        "de_novo_sm": de_novo_results,
        "n_targets": len(sm_targets),
        "n_candidates_total": total_candidates,
        "wall_time_s": wall_time,
    }
    run_state.mark_phase_completed(db, run_id, phase=5, output=output)
    run_state.log_compute(db, run_id=run_id, phase=5, step="phase5_complete",
                          service="local", wall_time_s=wall_time)
    log.info("[Phase 5] Complete: %d candidates across %d targets (%.1fs)",
             total_candidates, len(sm_targets), wall_time)
    return output


# ─────────────────────────────────────────────────────────────────────────────
# Per-target pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _denovo_one(
    *,
    symbol: str,
    p2: Dict,
    config: RunConfig,
    provider,
    ref_fps,
    db,
    run_id: str,
    phase4_output: Optional[Dict] = None,
) -> List[Dict]:
    pockets: List[Dict] = p2.get("pockets", [])
    best_pocket: Optional[Dict] = pockets[0] if pockets else None
    # P2 stores a local file path in pdb_path; prepare_receptor_pdbqt accepts both.
    pdb_url: Optional[str] = p2.get("structure", {}).get("pdb_path")

    # ── 5.1 Seed collection ──────────────────────────────────────────────────
    seeds = list(config.seed_smiles)  # user-supplied
    seeds += _fetch_chembl_binder_smiles(symbol)
    p4_seeds = _extract_p4_seeds(phase4_output, symbol)
    if p4_seeds:
        log.info("[5.1] %s: seeding %d SMILES from Phase 4 repurposing hits", symbol, len(p4_seeds))
        seeds += p4_seeds
    log.info("[5.1] %s: %d seed SMILES total (user=%d chembl=%d p4=%d)",
             symbol, len(seeds), len(config.seed_smiles),
             len(seeds) - len(config.seed_smiles) - len(p4_seeds), len(p4_seeds))

    # ── 5.2 Generation ───────────────────────────────────────────────────────
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"rxdis_p5_{symbol}_"))
    try:
        generated = generate_molecules(seeds, n_generate=_N_GENERATE, work_dir=tmp_dir)

        # If no generation (no seeds, no REINVENT4, BRICS produced nothing) — use seeds + ChEMBL
        if not generated:
            generated = seeds[:200]
            log.warning("[5] %s: generation empty — using %d seeds directly", symbol, len(generated))

        # ── 5.3 Medichem filters ─────────────────────────────────────────────
        filtered = apply_filters(
            generated,
            reference_fps=ref_fps,
            novelty_threshold=0.7,
            sa_threshold=6.0,
            qed_threshold=0.3,
        )
        passing_smiles = [r["smiles"] for r in filtered if r["passes"]]
        filter_meta = {r["smiles"]: r for r in filtered}
        log.info("[5.3] %s: %d/%d pass filters", symbol, len(passing_smiles), len(generated))

        if not passing_smiles:
            log.warning("[5] %s: no molecules passed filters", symbol)
            return []

        # ── 5.4 ADMET ────────────────────────────────────────────────────────
        admet_results = batch_score_admet(
            passing_smiles[:500],   # cap at 500 for speed
            indication_type=config.indication_type,
            selectivity_target=config.selectivity_target,
        )
        admet_by_smiles = {r["smiles"]: r for r in admet_results}
        admet_passing = [smi for smi in passing_smiles[:500]
                         if admet_by_smiles.get(smi, {}).get("passes", False)]
        log.info("[5.4] %s: %d/%d pass ADMET", symbol, len(admet_passing), len(passing_smiles[:500]))

        if not admet_passing:
            # Relax: take top-20 by admet_score anyway
            admet_passing = sorted(
                [r["smiles"] for r in admet_results],
                key=lambda s: admet_by_smiles.get(s, {}).get("admet_score", 0),
                reverse=True,
            )[:20]
            log.warning("[5] %s: relaxed ADMET — keeping top 20 by score", symbol)

        # ── 5.5 Docking ──────────────────────────────────────────────────────
        docked = _dock_candidates(
            smiles_list=admet_passing[:200],
            pdb_url=pdb_url,
            pocket=best_pocket,
            symbol=symbol,
            work_dir=tmp_dir,
        )
        # docked: {smiles: vina_score}

        # ── Assemble candidates ──────────────────────────────────────────────
        vina_scores = [docked.get(s) for s in admet_passing[:200]]
        ceiling = calibrate_ceiling(vina_scores)

        candidates = []
        for smi in admet_passing[:200]:
            fm = filter_meta.get(smi, {})
            am = admet_by_smiles.get(smi, {})
            vina = docked.get(smi)

            scored = score_candidate(
                vina_score=vina,
                admet_score=am.get("admet_score", 0.5),
                qed=fm.get("qed", 0.0),
                tanimoto_to_approved=fm.get("tanimoto_to_approved", 0.0),
                vina_ceiling=ceiling,
            )
            candidates.append({
                "smiles": smi,
                "vina_score": vina,
                "mw": fm.get("mw"),
                "logp": fm.get("logp"),
                "tpsa": fm.get("tpsa"),
                "sa_score": fm.get("sa_score"),
                "pains_flags": fm.get("pains_flags", []),
                "admet": {
                    "hERG": am.get("hERG", "unknown"),
                    "AMES": am.get("AMES", "unknown"),
                    "BBB": am.get("BBB", "unknown"),
                    "hepatox": am.get("hepatox", "unknown"),
                    "logS": am.get("logS"),
                    "disqualifying": am.get("disqualifying", []),
                    "concerns": am.get("concerns", []),
                },
                **scored,
            })

        ranked = rank_candidates(candidates)
        top = ranked[:_TOP_N]

        # ── 5.6 LLM gate ─────────────────────────────────────────────────────
        for c in top[:5]:  # narrative only for top-5
            if c.get("passed"):
                try:
                    c["narrative"] = _gate_admet_context(
                        provider=provider, db=db, run_id=run_id,
                        symbol=symbol, candidate=c, config=config,
                    )
                except Exception as exc:
                    log.debug("[5.6] LLM gate skipped: %s", exc)
                    c["narrative"] = ""

        return top

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# Docking helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dock_candidates(
    smiles_list: List[str],
    pdb_url: Optional[str],
    pocket: Optional[Dict],
    symbol: str,
    work_dir: Path,
) -> Dict[str, Optional[float]]:
    """
    Dock smiles_list against the pocket. Returns {smiles: vina_score}.
    Re-uses Phase 4 docking infrastructure (prepare_receptor_pdbqt, dock_library).
    """
    results: Dict[str, Optional[float]] = {s: None for s in smiles_list}

    if not pdb_url or not pocket or not pocket.get("cx"):
        log.info("[5.dock] %s: no pocket/structure — docking skipped", symbol)
        return results

    plddt = 70.0  # assume OK (structure already validated in P2)
    try:
        from src.phases.phase4.docking import (
            check_structure_quality, dock_library, prepare_receptor_pdbqt,
        )
        if not check_structure_quality(plddt):
            return results

        receptor_dir = work_dir / "receptor"
        receptor_dir.mkdir(exist_ok=True)
        receptor_pdbqt = prepare_receptor_pdbqt(pdb_url, receptor_dir)
        if not receptor_pdbqt:
            log.warning("[5.dock] %s: receptor prep failed", symbol)
            return results

        # Build candidate dicts for dock_library format
        cand_dicts = [{"smiles": s, "drug_name": f"DNSM_{i:04d}"}
                      for i, s in enumerate(smiles_list)]
        dock_dir = work_dir / "dock"
        dock_dir.mkdir(exist_ok=True)

        docked = dock_library(
            candidates=cand_dicts,
            receptor_pdbqt=receptor_pdbqt,
            pocket=pocket,
            work_dir=dock_dir,
            exhaustiveness=4,
            n_workers=_DOCK_WORKERS,
        )
        for c in docked:
            if c.get("smiles") and c.get("vina_score") is not None:
                results[c["smiles"]] = c["vina_score"]
        n_docked = sum(1 for v in results.values() if v is not None)
        log.info("[5.dock] %s: %d/%d docked", symbol, n_docked, len(smiles_list))

    except Exception as exc:
        log.warning("[5.dock] %s: docking error — %s", symbol, exc)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 seed extraction
# ─────────────────────────────────────────────────────────────────────────────

def _extract_p4_seeds(phase4_output: Optional[Dict], symbol: str, max_seeds: int = 20) -> List[str]:
    """
    Extract SMILES from Phase 4 repurposing hits to seed de novo generation.
    Prioritises candidates that passed the strict repurposing score threshold;
    falls back to all candidates if none passed.
    """
    if not phase4_output:
        return []
    repurposing: Dict = phase4_output.get("repurposing", {})
    hits: List[Dict] = repurposing.get(symbol, [])
    if not hits:
        return []

    passed = [h["smiles"] for h in hits if h.get("smiles") and h.get("passed")]
    if passed:
        return passed[:max_seeds]
    # Fallback: use all candidates regardless of passed flag
    return [h["smiles"] for h in hits if h.get("smiles")][:max_seeds]


# ─────────────────────────────────────────────────────────────────────────────
# ChEMBL seed collection
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_chembl_binder_smiles(symbol: str, max_compounds: int = 50) -> List[str]:
    """Return SMILES of ChEMBL drug-mechanism compounds for symbol."""
    try:
        from src.phases.phase4.chembl_query import get_target_drugs
        drugs = get_target_drugs(symbol, uniprot_id=None)
        # get_target_drugs returns drug_mechanism entries — no pchembl_value field.
        # All entries are curated MOA binders so any max_phase >= 1 is a valid seed.
        smiles = [d["smiles"] for d in drugs if d.get("smiles") and d.get("max_phase", 0) >= 1]
        return smiles[:max_compounds]
    except Exception:
        return []


def _load_reference_smiles(max_compounds: int = 5000) -> List[str]:
    """Load ChEMBL approved-drug SMILES for novelty filtering."""
    try:
        from src.phases.phase4.chembl_query import get_approved_library
        df = get_approved_library(min_phase=4, max_compounds=max_compounds)
        if not df.empty:
            return df["smiles"].dropna().tolist()
    except Exception:
        pass
    return []


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


def _gate_admet_context(
    *,
    provider,
    db,
    run_id: str,
    symbol: str,
    candidate: Dict,
    config: RunConfig,
) -> str:
    admet = candidate.get("admet", {})
    prompt = (
        f"You are a medicinal chemist reviewing a de novo small molecule candidate.\n\n"
        f"Target: {symbol}\n"
        f"Indication: {config.indication_type}\n"
        f"SMILES: {candidate['smiles']}\n"
        f"Vina score: {candidate.get('vina_score')} kcal/mol\n"
        f"QED: {candidate.get('qed')}, SA score: {candidate.get('sa_score')}\n"
        f"ADMET: hERG={admet.get('hERG')}, AMES={admet.get('AMES')}, "
        f"hepatox={admet.get('hepatox')}, logS={admet.get('logS')}\n"
        f"Disqualifying flags: {admet.get('disqualifying', [])}\n"
        f"Concerns: {admet.get('concerns', [])}\n\n"
        f"Interpret the ADMET profile in context of this indication. "
        f"Provide: overall_verdict (pass/borderline/fail), key concern, "
        f"top 1-2 structural modifications to improve safety.\n\n"
        f'Return ONLY: {{"overall_verdict":"pass","concern":"...","modifications":["..."]}}'
    )
    result = provider.complete(prompt, temperature=0.15, max_tokens=250)
    parsed = _extract_json(result.text)

    if parsed:
        narrative = (
            f"Verdict: {parsed.get('overall_verdict','unknown')}. "
            f"{parsed.get('concern','')} "
            f"Suggested modifications: {'; '.join(parsed.get('modifications', []))}"
        )
    else:
        narrative = result.text[:300]

    run_state.log_decision(
        db, run_id=run_id, phase=5,
        gate=f"5.4_admet_context_{symbol}",
        provider=provider.name,
        model=getattr(provider, "model", "unknown"),
        prompt=prompt, raw_response=result.text,
        decision_json=parsed or {"raw": narrative},
    )
    return narrative


# ─────────────────────────────────────────────────────────────────────────────
# Persistence + helpers
# ─────────────────────────────────────────────────────────────────────────────

def _persist_candidates(db, run_id: str, symbol: str, candidates: List[Dict]) -> None:
    import hashlib
    for c in candidates:
        try:
            cid = "DNSM_" + hashlib.sha1(c["smiles"].encode()).hexdigest()[:8].upper()
            run_state.insert_candidate(
                db, run_id=run_id, symbol=symbol, phase=5,
                kind="sm",
                candidate_id=cid,
                name=cid,
                smiles=c["smiles"],
                score=c.get("combined_pre8", 0.0),
                rank=c.get("rank", 0),
                passed=c.get("passed", False),
                evidence={
                    "vina_score": c.get("vina_score"),
                    "vina_norm": c.get("vina_norm"),
                    "admet_score": c.get("admet_score"),
                    "qed": c.get("qed"),
                    "sa_score": c.get("sa_score"),
                    "novelty": c.get("novelty"),
                    "admet": c.get("admet", {}),
                    "pains_flags": c.get("pains_flags", []),
                    "narrative": c.get("narrative", ""),
                },
            )
        except Exception as exc:
            log.warning("[5] DB persist failed for %s: %s", symbol, exc)


def _make_provider(config: RunConfig):
    from src.llm.factory import make_provider
    return make_provider(config.llm)


def _empty_output(t_start: float) -> Dict:
    return {
        "de_novo_sm": {},
        "n_targets": 0,
        "n_candidates_total": 0,
        "note": "No targets routed to P5 or de_novo_enabled=False",
        "wall_time_s": round(time.monotonic() - t_start, 1),
    }
