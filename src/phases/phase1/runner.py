"""
Phase 1 runner — Tabular PU-Learning architecture.

Replaces the NLP/literature map-reduce design (retired 2026-05-31).
See docs/PRD_phase1_target_id.md for the full specification.

Pipeline:
  1.1  Disease → EFO (existing disease_normalization.py, unchanged)
  1.2  Optional thin OT pull → tractability hints for Phase-2 compat
  1.3  Feature matrix assembly (matrix.py)
  1.4  PU learning: LightGBM bagging, AUROC, SHAP (pu_model.py)
  1.5  Causal filter: DoRothEA / decoupleR master-regulator (causal_filter.py)
  1.6  Genetic evidence → `genetic` compat key (genetic_evidence.py, reused)
  1.7  PPI eigenvector proxy → `ppi_eigenvector` compat key (STRING embedding dim 0)
  1.8  Rank, persist, emit output JSON

Phase-2 compatibility contract (do not break):
  evidence_trail keys required by Phase 2:
    tractability     → phase2/runner.py:82  (pocket druggability fallback)
    genetic          → phase2/scoring.py:60 (genetic evidence feature)
    ppi_eigenvector  → phase2/scoring.py:61 (network centrality feature)
  All three are populated here even when their source is unavailable (default 0.0).
"""
from __future__ import annotations
import logging
import time
from typing import Any, Dict, List, Optional

from src.config.run_config import RunConfig
from src.db import run_state
from src.llm.factory import make_provider

from .disease_normalization import normalize_disease
from .matrix import build_feature_matrix
from .pu_model import run_pu_learning, get_top_shap
from .causal_filter import annotate_master_regulators
from .genetic_evidence import (
    get_gwas_evidence, get_omim_evidence, get_diseases_evidence, merge_genetic_evidence,
)

log = logging.getLogger(__name__)

# PU probability threshold below which genes are excluded from the ranked list
# (keeps the output focused; all positives/seed_targets bypass this).
_PU_SCORE_FLOOR = 0.50


def run_phase1(
    run_id: str,
    config: RunConfig,
    db,
    phase0_output: Dict,
    lit_max_abstracts: int = 0,   # ignored — kept for signature compat with kickoff.py
) -> Dict[str, Any]:
    """Execute Phase 1. Returns the standardised output JSON."""
    if phase0_output.get("go_no_go") != "go":
        raise RuntimeError("Phase 0 did not return go_no_go='go'. Run Phase 0 first.")

    run_state.mark_phase_running(db, run_id, phase=1)
    t_start = time.monotonic()

    provider = make_provider(config.llm)
    seed_set = set(config.seed_targets)
    exclude_set = set(config.exclude_targets)
    disease = config.disease_name

    # known_positives: the PU anchor (new field). Fallback to seed_targets.
    known_positives: List[str] = list(
        getattr(config, "known_positives", None) or config.seed_targets or []
    )
    if not known_positives:
        log.warning(
            "[1] No known_positives or seed_targets provided. "
            "The PU model will have no positives and cannot score. "
            "Please set known_positives in your RunConfig."
        )

    # ── 1.1 Disease normalization ─────────────────────────────────────────────
    if config.disease_efo_id:
        efo_id = config.disease_efo_id
        disease_label = disease
        log.info("[1.1] Using provided EFO: %s", efo_id)
    else:
        log.info("[1.1] Normalizing disease: '%s'", disease)
        efo_id, disease_label = normalize_disease(disease, provider, db, run_id)

    db.table("runs").update({"efo_id": efo_id}).eq("id", run_id).execute()

    # ── 1.2 OT pull — tractability + genetic_association score + DOID cross-refs ─
    # Phase 2 uses tractability as a pocket-druggability fallback.
    # genetic_association (the OT genetics portal score) feeds step 1.6 as a
    # high-quality supplement to GWAS/OMIM/DISEASES — it's already computed by OT
    # and exposed in datatypeScores with zero additional API cost.
    # We also capture DOID cross-refs so the Jensen DISEASES lookup can match by ID.
    tractability_map: Dict[str, float] = {}
    ot_genetic_map: Dict[str, float] = {}
    disease_doid_ids: List[str] = []
    try:
        from .open_targets import pull_ot_associations, get_disease_xrefs
        log.info("[1.2] OT pull (tractability + genetic scores) for '%s'", efo_id)
        ot_targets = pull_ot_associations(
            efo_id, min_score=0.05, cap=300,
            seed_targets=set(known_positives) | seed_set,
            exclude_targets=exclude_set,
        )
        for t in ot_targets:
            sym = t["symbol"]
            tractability_map[sym] = float(t.get("tractability_max", 0.0))
            ga = t.get("dt_scores", {}).get("genetic_association", 0.0)
            if ga:
                ot_genetic_map[sym] = round(float(ga), 4)
        # Fetch DOID cross-references for this disease (used in Jensen DISEASES lookup)
        disease_doid_ids = get_disease_xrefs(efo_id, prefix="DOID")
        log.info("[1.2] OT: %d genes tractability, %d genetic scores, %d DOID xrefs",
                 len(tractability_map), len(ot_genetic_map), len(disease_doid_ids))
    except Exception as exc:
        log.warning("[1.2] OT pull failed (%s) — tractability/genetic defaults to 0.0", exc)

    # ── 1.3 Feature matrix assembly ───────────────────────────────────────────
    log.info("[1.3] Assembling feature matrix…")
    matrix = build_feature_matrix()

    # ── 1.4 PU learning ──────────────────────────────────────────────────────
    if not known_positives:
        raise RuntimeError(
            "Cannot run PU model with zero known_positives. "
            "Set known_positives or seed_targets in RunConfig."
        )

    # Verify positives are in the matrix; warn on any that aren't.
    valid_positives = [p for p in known_positives if p in matrix.index]
    missing = set(known_positives) - set(valid_positives)
    if missing:
        log.warning("[1.4] known_positives not in gene universe: %s", missing)
    if not valid_positives:
        raise RuntimeError(
            f"None of known_positives {known_positives} found in gene universe. "
            "Check gene symbol spelling (must be HGNC)."
        )

    log.info("[1.4] Running PU learning (%d positives)…", len(valid_positives))
    pu_result, shap_map = run_pu_learning(
        matrix, valid_positives,
        n_bags=getattr(config, "pu_n_bags", 30),
        random_state=42,
    )
    auroc = pu_result.attrs.get("auroc_loo", float("nan"))
    log.info("[1.4] AUROC(LOO): %.3f", auroc)

    # ── 1.5 Causal filter on top candidates ──────────────────────────────────
    pre_rank_n = min(len(pu_result), max(config.target_count_max * 5, 200))
    top_symbols = pu_result["symbol"].head(pre_rank_n).tolist()
    log.info("[1.5] Annotating master regulators for top %d genes…", len(top_symbols))
    causal_map = annotate_master_regulators(top_symbols)

    # ── 1.6 Genetic evidence → `genetic` compat key ───────────────────────────
    log.info("[1.6] Fetching genetic evidence (GWAS + OMIM + Jensen DISEASES)…")
    genetic_map: Dict[str, float] = {}
    try:
        gwas_ev      = get_gwas_evidence(efo_id, disease)
        omim_ev      = get_omim_evidence(top_symbols)
        diseases_ev  = get_diseases_evidence(disease, doid_ids=disease_doid_ids)
        merged       = merge_genetic_evidence(gwas_ev, omim_ev, diseases_ev)
        for sym, gdata in merged.items():
            # Take the best of: merged genetic evidence OR OT genetic_association score
            base = float(gdata.get("genetic_score", 0.0))
            ot_ga = ot_genetic_map.get(sym, 0.0)
            genetic_map[sym] = round(max(base, ot_ga * 0.8), 4)
        log.info("[1.6] Genetic evidence: %d genes (GWAS=%d OMIM=%d DISEASES=%d OT-GA=%d)",
                 len(genetic_map), len(gwas_ev), len(omim_ev), len(diseases_ev), len(ot_genetic_map))
    except Exception as exc:
        log.warning("[1.6] Genetic evidence failed (%s) — genetic compat key = 0.0", exc)

    # ── 1.7 PPI eigenvector proxy ─────────────────────────────────────────────
    # The spectral embedding dimension 0 is proportional to eigenvector centrality
    # of the symmetric-normalised adjacency (first right-singular vector of A_norm).
    # We min-max normalise it to [0, 1] so it matches the scale Phase 2 expects.
    ppi_map: Dict[str, float] = {}
    try:
        emb0 = matrix["emb_0"]
        emb0_min, emb0_max = float(emb0.min()), float(emb0.max())
        span = emb0_max - emb0_min or 1.0
        for sym in top_symbols:
            if sym in matrix.index:
                ppi_map[sym] = float((emb0[sym] - emb0_min) / span)
    except Exception as exc:
        log.warning("[1.7] PPI proxy failed (%s) — ppi_eigenvector compat key = 0.0", exc)

    # ── 1.7b Surface raw omics features for the UI scorecard ───────────────────
    # These are display-only (Phase 2 re-derives its own essentiality); additive,
    # so they never break the Phase-2 compat contract.
    def _feat(sym: str, col: str) -> float:
        try:
            if col in matrix.columns and sym in matrix.index:
                return round(float(matrix.at[sym, col]), 4)
        except Exception:
            pass
        return 0.0

    # ── 1.8 Rank, threshold, build output rows ────────────────────────────────
    # NOTE: iterate with itertuples (NOT iterrows). iterrows builds a Series per
    # row and deep-copies the frame's .attrs each time; itertuples is ~100x faster
    # and attrs-free. Combined with keeping the SHAP map out of .attrs, this keeps
    # ranking over ~20k genes well under a second.
    log.info("[1.8] Ranking %d genes and assembling evidence trails…", len(pu_result))
    always_include = (set(valid_positives) | seed_set) - exclude_set
    ranked: List[Dict] = []
    rank_counter = 1

    for row in pu_result.itertuples(index=False):
        sym = row.symbol
        if sym in exclude_set:
            continue
        is_seeded = sym in always_include or bool(row.is_positive)
        prob = float(row.pu_probability)
        if prob < _PU_SCORE_FLOOR and not is_seeded:
            continue
        if rank_counter > config.target_count_max and not is_seeded:
            continue

        causal = causal_map.get(sym, {})
        shap_top = get_top_shap(shap_map, sym, matrix.index)

        evidence_trail = {
            # ── PU-specific (new) ─────────────────────────────────────────────
            "xgb_probability": round(prob, 6),
            "pu_percentile": round(float(row.pu_percentile), 6),
            "dorothea_activity": round(causal.get("dorothea_activity", 0.0), 4),
            "is_master_regulator": causal.get("is_master_regulator", False),
            "regulon_size": causal.get("regulon_size", 0),
            "dorothea_confidence": causal.get("dorothea_confidence", ""),
            "shap_top": shap_top[:10],
            # ── Raw omics (display-only, additive) ────────────────────────────
            "essentiality": _feat(sym, "chronos_median"),
            "selective_fraction": _feat(sym, "selective_fraction"),
            "expression": _feat(sym, "gtex_log_mean_tpm"),
            # ── Phase-2 compat keys (REQUIRED — do not remove) ────────────────
            "tractability": tractability_map.get(sym, 0.0),
            "genetic": genetic_map.get(sym, 0.0),
            "ppi_eigenvector": ppi_map.get(sym, 0.0),
        }

        ranked.append({
            "rank": rank_counter,
            "ensembl_id": "",          # PU pipeline is symbol-keyed; blank is valid
            "symbol": sym,
            "aggregate_score": round(prob, 6),
            "modality_hint": "unknown",   # Phase 3 will decide
            "tdl": "unknown",             # Pharos not called in this arch
            "seeded": is_seeded,
            "evidence_trail": evidence_trail,
        })
        rank_counter += 1

    # Seeded targets always appear even if below floor.
    existing_syms = {t["symbol"] for t in ranked}
    for sym in always_include - existing_syms:
        if sym in exclude_set:
            continue
        prob_row = pu_result[pu_result["symbol"] == sym]
        prob = float(prob_row["pu_probability"].values[0]) if len(prob_row) else 0.0
        causal = causal_map.get(sym, {})
        shap_top = get_top_shap(shap_map, sym, matrix.index)
        ranked.append({
            "rank": rank_counter,
            "ensembl_id": "",
            "symbol": sym,
            "aggregate_score": round(prob, 6),
            "modality_hint": "unknown",
            "tdl": "unknown",
            "seeded": True,
            "evidence_trail": {
                "xgb_probability": round(prob, 6),
                "pu_percentile": 0.0,
                "dorothea_activity": round(causal.get("dorothea_activity", 0.0), 4),
                "is_master_regulator": causal.get("is_master_regulator", False),
                "regulon_size": causal.get("regulon_size", 0),
                "dorothea_confidence": causal.get("dorothea_confidence", ""),
                "shap_top": shap_top[:10],
                "essentiality": _feat(sym, "chronos_median"),
                "selective_fraction": _feat(sym, "selective_fraction"),
                "expression": _feat(sym, "gtex_log_mean_tpm"),
                "tractability": tractability_map.get(sym, 0.0),
                "genetic": genetic_map.get(sym, 0.0),
                "ppi_eigenvector": ppi_map.get(sym, 0.0),
            },
        })
        rank_counter += 1

    # ── Write to DB ───────────────────────────────────────────────────────────
    log.info("[1.8] Persisting %d ranked targets to the database…", len(ranked))
    run_state.clear_targets(db, run_id)  # wipe any prior rows for this run first
    for t in ranked:
        run_state.upsert_target(
            db,
            run_id=run_id,
            rank=t["rank"],
            ensembl_id=t["ensembl_id"],
            symbol=t["symbol"],
            aggregate_score=t["aggregate_score"],
            tdl=t["tdl"],
            modality_hint=t["modality_hint"],
            seeded=t["seeded"],
            evidence_trail=t["evidence_trail"],
        )

    # ── Output JSON ───────────────────────────────────────────────────────────
    wall_time = round(time.monotonic() - t_start, 1)
    output = {
        "ranked_targets": ranked,
        "efo_id": efo_id,
        "disease_label": disease_label,
        "model": {
            "method": "bagging-PU",
            "estimator": "lightgbm",
            "auroc_loo": round(auroc, 4) if auroc == auroc else None,
            "n_positives": len(valid_positives),
            "n_genes": len(matrix),
        },
        "causal_filter": {
            "n_master_regulators": sum(
                1 for v in causal_map.values() if v.get("is_master_regulator")
            ),
        },
        "feature_matrix": {
            "rows": len(matrix),
            "cols": len(matrix.columns),
            "peak_ram_mb": round(matrix.memory_usage(deep=True).sum() / 1e6, 1),
        },
        "wall_time_s": wall_time,
    }

    run_state.mark_phase_completed(db, run_id, phase=1, output=output)
    run_state.log_compute(
        db, run_id=run_id, phase=1,
        step="phase1_complete", service="local", wall_time_s=wall_time,
    )
    log.info(
        "[Phase 1] Complete: %d targets in %.1fs (AUROC %.3f). Top-5: %s",
        len(ranked), wall_time, auroc if auroc == auroc else 0,
        [t["symbol"] for t in ranked[:5]],
    )
    return output
