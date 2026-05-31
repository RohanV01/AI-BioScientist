"""
Phase 2 runner — per-target validation orchestration.

For each Phase 1 ranked target it assembles a biophysical profile (essentiality,
structure, pockets, variants, localization, expression, chemical matter), scores
modality eligibility, computes a validation_score with feature attributions, and
decides whether the target advances to Phase 3.

Pass rule (PRD 2.9): validation_score > 0.5 → pass. Seeded targets always pass
(flagged). If fewer than 3 pass, the threshold is lowered to 0.3 with a warning.
"""
from __future__ import annotations
import logging
import time
from typing import Any, Dict, List

from src.config.run_config import RunConfig
from src.llm.factory import make_provider
from src.db import run_state

from . import uniprot as uniprot_mod
from . import essentiality as ess_mod
from . import structure as struct_mod
from . import pockets as pocket_mod
from . import variants as variant_mod
from . import localization as loc_mod
from . import expression as expr_mod
from . import chembl as chembl_mod
from . import tractability as tract_mod
from . import scoring as score_mod

log = logging.getLogger(__name__)

_PASS_THRESHOLD = 0.5
_FALLBACK_THRESHOLD = 0.3
_MIN_PASS = 3


def run_phase2(run_id: str, config: RunConfig, db, phase1_output: Dict) -> Dict[str, Any]:
    ranked = phase1_output.get("ranked_targets", [])
    if not ranked:
        raise RuntimeError("Phase 2 requires Phase 1 ranked_targets; none found.")

    run_state.mark_phase_running(db, run_id, phase=2)
    t_start = time.monotonic()
    provider = make_provider(config.llm)
    seed_set = set(config.seed_targets)

    # Validate the top-N targets.
    targets = ranked[: config.target_count_max]
    symbols = [t["symbol"] for t in targets]
    log.info("[Phase 2] Validating %d targets: %s", len(targets), symbols)

    # ── Batch lookups (single pass over big local files) ──────────────────────
    ess_map = ess_mod.batch_essentiality(symbols)

    # Resolve UniProt first (needed for variant batch + structure + chembl).
    uniprot_map: Dict[str, Dict] = {}
    for t in targets:
        meta = uniprot_mod.resolve_uniprot(t["symbol"], t.get("ensembl_id", ""))
        if meta:
            uniprot_map[t["symbol"]] = meta

    accs = [uniprot_map[s]["uniprot"] for s in symbols if s in uniprot_map]
    variant_by_acc = variant_mod.get_variant_burden_batch(accs)

    # ── Per-target validation ─────────────────────────────────────────────────
    validated: List[Dict] = []
    artifacts: List[str] = []

    for t in targets:
        sym = t["symbol"]
        ensembl = t.get("ensembl_id", "")
        meta = uniprot_map.get(sym)
        acc = meta["uniprot"] if meta else None
        seq = meta.get("sequence", "") if meta else ""

        localization = loc_mod.classify_localization(sym, ensembl, meta)
        structure = struct_mod.acquire_structure(sym, acc, seq)
        pockets = pocket_mod.detect_pockets(
            sym, structure.get("pdb_path"),
            t.get("evidence_trail", {}).get("tractability", 0.0),
        )
        variants = variant_by_acc.get(acc, {
            "high_path_missense": 0, "total_scored": 0,
            "pathogenic_fraction": 0.0, "source": "none"}) if acc else {
            "high_path_missense": 0, "total_scored": 0,
            "pathogenic_fraction": 0.0, "source": "none"}
        expression = expr_mod.get_expression_safety(sym, ensembl, config.tissue_of_interest)
        chembl = chembl_mod.chemical_matter(acc)
        essentiality = ess_map.get(sym, {})

        modality = tract_mod.assess_modality(
            symbol=sym, localization=localization, pockets=pockets, chembl=chembl,
            variants=variants, structure=structure,
            selectivity_target=config.selectivity_target,
            provider=provider, db=db, run_id=run_id,
        )

        features = score_mod.build_features(
            indication_type=config.indication_type,
            essentiality=essentiality, structure=structure, pockets=pockets,
            modality=modality, variants=variants, expression=expression,
            phase1_evidence=t.get("evidence_trail", {}),
        )
        scored = score_mod.compute_validation_score(
            features, indication_type=config.indication_type,
            essentiality=essentiality, variants=variants,
        )

        facts = {
            "structure_source": structure.get("source"),
            "median_plddt": structure.get("median_plddt"),
            "compartment": localization.get("compartment"),
            "max_druggability": pockets.get("max_druggability"),
            "chronos_median": essentiality.get("chronos_median"),
            "high_path_missense": variants.get("high_path_missense"),
            "primary_modality": modality.get("primary"),
            "critical_tissue_flag": expression.get("critical_tissue_flag"),
        }
        narrative = score_mod.generate_narrative(
            sym, scored["validation_score"], scored["attributions"], facts,
            provider, db, run_id,
        )

        if structure.get("pdb_path"):
            artifacts.append(structure["pdb_path"])

        validated.append({
            "symbol": sym,
            "ensembl_id": ensembl,
            "uniprot": acc,
            "validation_score": scored["validation_score"],
            "seeded": t.get("seeded", False) or sym in seed_set,
            "structure": {
                "source": structure.get("source"),
                "uniprot": acc,
                "pdb_id": structure.get("pdb_id"),
                "median_plddt": structure.get("median_plddt"),
                "low_confidence": structure.get("low_confidence"),
                "ordered_ranges": structure.get("ordered_ranges"),
            },
            "pockets": pockets.get("pockets"),
            "max_druggability": pockets.get("max_druggability"),
            "sm_branch_enabled": pockets.get("sm_branch_enabled"),
            "pocket_detection": pockets.get("detection"),
            "essentiality": essentiality,
            "variants": variants,
            "localization": localization,
            "safety": {
                "critical_tissue_flag": expression.get("critical_tissue_flag"),
                "tsi": expression.get("tsi"),
                "tissue_specificity": expression.get("tissue_specificity"),
                "broadly_expressed": expression.get("broadly_expressed"),
            },
            "chembl": chembl,
            "modality": {
                "scores": modality.get("scores"),
                "primary": modality.get("primary"),
                "secondary": modality.get("secondary"),
                "edge_case": modality.get("edge_case"),
                "off_target_hazards": modality.get("off_target_hazards"),
            },
            "features": features,
            "attributions": scored["attributions"],
            "modifiers_applied": scored["modifiers_applied"],
            "evidence_summary": narrative,
        })

    # ── Pass / fail thresholding ──────────────────────────────────────────────
    threshold = _PASS_THRESHOLD
    passing = [v for v in validated if v["validation_score"] > threshold or v["seeded"]]
    if len([v for v in passing if not v["seeded"]]) < _MIN_PASS:
        threshold = _FALLBACK_THRESHOLD
        passing = [v for v in validated if v["validation_score"] > threshold or v["seeded"]]
        log.warning("[Phase 2] <%d targets passed 0.5 — lowered threshold to %.1f",
                    _MIN_PASS, _FALLBACK_THRESHOLD)

    for v in validated:
        v["passed"] = v["validation_score"] > threshold or v["seeded"]

    # ── Persist ───────────────────────────────────────────────────────────────
    for v in validated:
        try:
            run_state.update_target_validation(
                db, run_id=run_id, symbol=v["symbol"],
                validation_score=v["validation_score"],
                modality_primary=v["modality"]["primary"],
                modality_secondary=v["modality"]["secondary"],
                evidence_trail={"phase2": {k: v[k] for k in (
                    "structure", "max_druggability", "essentiality", "variants",
                    "localization", "safety", "modality", "attributions",
                    "evidence_summary", "passed")}},
            )
        except Exception as exc:
            log.warning("[Phase 2] DB update failed for %s: %s", v["symbol"], exc)

    output = {
        "validated_targets": validated,
        "passing_symbols": [v["symbol"] for v in validated if v["passed"]],
        "threshold_used": threshold,
        "n_validated": len(validated),
        "n_passed": sum(1 for v in validated if v["passed"]),
        "wall_time_s": round(time.monotonic() - t_start, 1),
    }

    run_state.mark_phase_completed(db, run_id, phase=2, output=output, artifacts=artifacts)
    run_state.log_compute(db, run_id=run_id, phase=2, step="phase2_complete",
                          service="local", wall_time_s=output["wall_time_s"])

    log.info("[Phase 2] Complete: %d/%d passed (threshold %.1f) in %.1fs",
             output["n_passed"], output["n_validated"], threshold, output["wall_time_s"])
    return output
