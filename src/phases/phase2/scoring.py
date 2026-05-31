"""
Phase 2.9 — Aggregate validation score + feature attributions + narrative.

The PRD specifies XGBoost over STRING centralities + Node2Vec vs DepMap labels
with GradientSHAP attributions (AUROC ≈ 0.93 reference). xgboost/shap/sklearn are
not installed in this environment, so we use a **transparent linear surrogate**:
each normalised feature contributes `weight × value` to the score, and those
per-feature contributions ARE the attributions (a faithful, if simpler, Shapley
value for an additive model). When xgboost+shap become available this function is
the single swap point — same inputs, same output contract.

indication_type modifiers (PRD 2.1 / 2.9):
  - core-essential + non-oncology → ×0.75 (systemic-tox liability)
  - oncology rewards *selective* essentiality
  - ≥10 high-pathogenicity missense (disease-segregating proxy) → +10% boost
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

from src.llm.provider import LLMProvider
from src.db.run_state import log_decision
from .schemas import ShapNarrative

log = logging.getLogger(__name__)

_WEIGHTS = {
    "tractability": 0.25,
    "structure": 0.15,
    "essentiality": 0.15,
    "genetic": 0.15,
    "ppi_centrality": 0.10,
    "variant_support": 0.05,
    "safety": 0.15,
}


def build_features(
    *,
    indication_type: str,
    essentiality: Dict,
    structure: Dict,
    pockets: Dict,
    modality: Dict,
    variants: Dict,
    expression: Dict,
    phase1_evidence: Dict,
) -> Dict[str, float]:
    """Reduce the biophysical profile to seven normalised [0,1] features."""
    # Tractability = best achievable across any modality (not SM-only).
    tractability = max(modality.get("scores", {}).values() or [0.0])

    # Structure confidence.
    plddt = structure.get("median_plddt")
    structure_conf = (plddt / 100.0) if plddt is not None else 0.4

    # Essentiality appropriateness depends on indication.
    essentiality_feat = _essentiality_feature(indication_type, essentiality)

    genetic = float(phase1_evidence.get("genetic", 0.0))
    ppi = float(phase1_evidence.get("ppi_eigenvector", 0.0))

    variant_support = min(1.0, variants.get("high_path_missense", 0) / 20.0)

    # Safety: specificity + absence of critical-tissue expression.
    tsi = expression.get("tsi", 0.5)
    critical = 1.0 if expression.get("critical_tissue_flag") else 0.0
    safety = max(0.0, 0.5 * tsi + 0.5 * (1.0 - critical))

    return {
        "tractability": round(tractability, 4),
        "structure": round(min(1.0, structure_conf), 4),
        "essentiality": round(essentiality_feat, 4),
        "genetic": round(min(1.0, genetic), 4),
        "ppi_centrality": round(min(1.0, ppi), 4),
        "variant_support": round(variant_support, 4),
        "safety": round(safety, 4),
    }


def _essentiality_feature(indication_type: str, ess: Dict) -> float:
    if not ess.get("is_in_depmap"):
        return 0.5  # unknown → neutral
    sel = ess.get("selective_fraction", 0.0)
    if indication_type == "oncology":
        # Selective dependency is good; pan-essential is less attractive (tox).
        return sel * (0.6 if ess.get("is_core_essential") else 1.0)
    # Non-oncology: any essentiality is a liability.
    return max(0.0, 1.0 - sel)


def compute_validation_score(
    features: Dict[str, float],
    *,
    indication_type: str,
    essentiality: Dict,
    variants: Dict,
) -> Dict:
    """
    Returns {validation_score, attributions, modifiers_applied}.
    attributions are normalised per-feature contributions (∑ = 1.0).
    """
    contributions = {k: _WEIGHTS[k] * features.get(k, 0.0) for k in _WEIGHTS}
    base = sum(contributions.values())

    modifiers = []
    score = base

    # Core-essential + non-oncology → systemic-tox penalty.
    if essentiality.get("is_core_essential") and indication_type != "oncology":
        score *= 0.75
        modifiers.append("core_essential_nononc_-25%")

    # Disease-segregating pathogenic missense → boost.
    if variants.get("high_path_missense", 0) >= 10:
        score = min(1.0, score * 1.10)
        modifiers.append("pathogenic_missense_+10%")

    score = round(max(0.0, min(1.0, score)), 4)

    total = sum(contributions.values()) or 1.0
    attributions = {k: round(v / total, 4) for k, v in contributions.items()}

    return {
        "validation_score": score,
        "attributions": attributions,
        "modifiers_applied": modifiers,
    }


def generate_narrative(
    symbol: str,
    score: float,
    attributions: Dict[str, float],
    facts: Dict,
    provider: Optional[LLMProvider],
    db=None,
    run_id: str = "",
) -> str:
    """LLM gate 2.9 — feature attributions → plain-English evidence summary."""
    if provider is None:
        # Deterministic fallback summary.
        top = sorted(attributions.items(), key=lambda kv: kv[1], reverse=True)[:3]
        drivers = ", ".join(f"{k} ({v:.0%})" for k, v in top)
        return (f"{symbol} validation score {score:.2f}. Top contributors: {drivers}. "
                f"Structure: {facts.get('structure_source')} "
                f"(pLDDT {facts.get('median_plddt')}); "
                f"localization: {facts.get('compartment')}; "
                f"primary modality: {facts.get('primary_modality')}.")

    prompt = (
        f"Summarise the in-silico validation of drug target {symbol} in 2-3 sentences "
        f"for a drug discovery scientist.\n\n"
        f"Validation score: {score:.2f}\n"
        f"Feature attributions (relative): {attributions}\n"
        f"Structure: {facts.get('structure_source')} median pLDDT {facts.get('median_plddt')}\n"
        f"Localization: {facts.get('compartment')}\n"
        f"Max druggability: {facts.get('max_druggability')}\n"
        f"Essentiality (Chronos median): {facts.get('chronos_median')}\n"
        f"High-pathogenicity missense: {facts.get('high_path_missense')}\n"
        f"Primary modality: {facts.get('primary_modality')}\n"
        f"Critical-tissue flag: {facts.get('critical_tissue_flag')}\n\n"
        "Be specific about what makes it a strong or weak target. No preamble."
    )
    try:
        result = provider.complete(prompt, schema=ShapNarrative, temperature=0.2)
    except Exception as exc:
        log.warning("[2.9] %s narrative failed: %s", symbol, exc)
        return f"{symbol} validation score {score:.2f}."
    if not result.parsed:
        return f"{symbol} validation score {score:.2f}."
    if db:
        log_decision(db, run_id=run_id, phase=2, gate="2.9_shap_narrative",
                     provider=provider.name, model=provider.model,
                     prompt=prompt, raw_response=result.text, decision_json=result.parsed)
    return result.parsed.get("summary", f"{symbol} validation score {score:.2f}.")
