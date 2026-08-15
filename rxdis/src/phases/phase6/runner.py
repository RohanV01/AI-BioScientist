"""
Phase 6 — De Novo Biologic / Peptide Design runner.

Pipeline per target:
  6.1  Interface context extraction from Phase 2 structure + variants
  6.2  Sequence generation — RFdiffusion NIM → BoltzGen → LLM fallback
  6.3  Developability filter — aggregation / solubility / immunogenicity
  6.4  LLM gates — hotspot selection, immunogenicity report
  Rank by developability_score and persist top-10 per target.

Runs when P6_biologic is in routing branches
AND intent_mode in {explore, de_novo}.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from src.config.run_config import RunConfig
from src.db import run_state

from .developability import batch_assess
from .interface_analysis import build_interface_context
from .peptide_gen import generate_peptides

log = logging.getLogger(__name__)

_TOP_N = int(os.environ.get("P6_TOP_N", "10"))
_N_GENERATE = int(os.environ.get("P6_N_GENERATE", "30"))


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_phase6(
    run_id: str,
    config: RunConfig,
    db,
    phase2_output: Dict,
    phase3_output: Dict,
    phase1_output: Optional[Dict] = None,
) -> Dict[str, Any]:
    from src.phases.base_runner import PhaseGuard
    t_start = time.monotonic()
    with PhaseGuard(db, run_id, phase=6, config=config) as guard:
        guard.check_budget()
        guard.validate_input(phase2_output, ["validated_targets"], source_phase=2)
        guard.validate_input(phase3_output, ["routing"], source_phase=3)
        return _run_phase6_body(
            run_id=run_id, config=config, db=db,
            phase1_output=phase1_output,
            phase2_output=phase2_output,
            phase3_output=phase3_output,
            t_start=t_start,
        )


def _run_phase6_body(
    run_id: str, config: RunConfig, db,
    phase1_output: Optional[Dict], phase2_output: Dict,
    phase3_output: Dict, t_start: float,
) -> Dict[str, Any]:
    provider = _make_provider(config)

    p2_by_symbol: Dict[str, Dict] = {
        t["symbol"]: t for t in phase2_output.get("validated_targets", [])
    }

    bio_targets = [
        r for r in phase3_output.get("routing", [])
        if "P6_biologic" in r.get("branches", [])
    ]
    log.info("[Phase 6] Biologic design for %d targets", len(bio_targets))

    if not bio_targets or not config.de_novo_enabled:
        out = _empty_output(t_start)
        run_state.mark_phase_completed(db, run_id, phase=6, output=out)
        return out

    biologic_results: Dict[str, List[Dict]] = {}
    total_candidates = 0

    for routing in bio_targets:
        symbol: str = routing["symbol"]
        p2: Dict = p2_by_symbol.get(symbol, {})
        t0 = time.monotonic()
        log.info("[6] → %s", symbol)

        try:
            hits = _biologic_one(
                symbol=symbol,
                p2=p2,
                config=config,
                provider=provider,
                db=db,
                run_id=run_id,
            )
        except Exception as exc:
            log.error("[6] %s failed: %s", symbol, exc, exc_info=True)
            hits = []

        biologic_results[symbol] = hits
        total_candidates += len(hits)
        _persist_candidates(db, run_id, symbol, hits)
        log.info("[6] %s: %d candidates (%.1fs)", symbol, len(hits), time.monotonic() - t0)

    wall_time = round(time.monotonic() - t_start, 1)
    output = {
        "biologic": biologic_results,
        "n_targets": len(bio_targets),
        "n_candidates_total": total_candidates,
        "wall_time_s": wall_time,
    }
    run_state.mark_phase_completed(db, run_id, phase=6, output=output)
    run_state.log_compute(db, run_id=run_id, phase=6, step="phase6_complete",
                          service="local", wall_time_s=wall_time)
    log.info("[Phase 6] Complete: %d candidates across %d targets (%.1fs)",
             total_candidates, len(bio_targets), wall_time)
    return output


# ─────────────────────────────────────────────────────────────────────────────
# Per-target pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _biologic_one(
    *,
    symbol: str,
    p2: Dict,
    config: RunConfig,
    provider,
    db,
    run_id: str,
) -> List[Dict]:

    # ── 6.1 Interface context ────────────────────────────────────────────────
    interface_ctx = build_interface_context(symbol, p2)
    log.info("[6.1] %s: class=%s strategy=%s cyclic=%s",
             symbol, interface_ctx["target_class"],
             interface_ctx["design_strategy"],
             interface_ctx["cyclic_preferred"])

    # ── LLM gate: hotspot selection ─────────────────────────────────────────
    llm_hotspots = _gate_hotspot_selection(
        provider=provider, db=db, run_id=run_id,
        symbol=symbol, interface_ctx=interface_ctx,
    )
    if llm_hotspots:
        interface_ctx["hotspots"] = llm_hotspots

    # ── 6.2 Sequence generation ──────────────────────────────────────────────
    sequences = generate_peptides(
        symbol=symbol,
        interface_ctx=interface_ctx,
        provider=provider,
        n_sequences=_N_GENERATE,
    )
    if not sequences:
        log.warning("[6] %s: no sequences generated", symbol)
        return []

    # ── 6.3 Refolding validation (ipTM gate) — Boltz-1 CPU ───────────────────
    # P2 stores a local file path; pass it as the pdb_url argument (refolding accepts either).
    pdb_url = interface_ctx.get("pdb_path")
    refolding_by_seq: Dict[str, Dict] = {}

    if pdb_url:
        from src.config import settings as _settings
        sequences, refolding_by_seq = _run_refolding_validation(
            sequences=sequences,
            pdb_url=pdb_url,
            neurosnap_key=getattr(_settings, "NEUROSNAP_API_KEY", ""),
            nim_key=getattr(_settings, "NIM_API_KEY", ""),
            provider=provider,
            db=db,
            run_id=run_id,
            symbol=symbol,
        )
        log.info("[6.3] %s: refolding done — %d/%d passed ipTM gate",
                 symbol,
                 sum(1 for r in refolding_by_seq.values() if r.get("passes")),
                 len(refolding_by_seq))
    else:
        log.info("[6.3] %s: no PDB URL — refolding skipped, developability only", symbol)

    # ── 6.3 Developability ───────────────────────────────────────────────────
    dev_results = batch_assess(
        sequences,
        target_class=interface_ctx["target_class"],
        indication_type=config.indication_type,
        cyclic_preferred=interface_ctx["cyclic_preferred"],
    )
    passing = [r for r in dev_results if r["passes"]]
    log.info("[6.3] %s: %d/%d sequences pass developability",
             symbol, len(passing), len(sequences))

    if not passing:
        # Relax: take top-5 by developability_score
        passing = sorted(dev_results,
                         key=lambda r: r.get("developability_score", 0),
                         reverse=True)[:5]
        log.warning("[6] %s: relaxed gate — top 5 by score", symbol)

    # Build candidate dicts
    candidates = []
    for i, r in enumerate(passing[:_TOP_N]):
        seq = r["sequence"]
        refold = refolding_by_seq.get(seq, {})

        # combined_pre8: if ipTM available weight it heavily; else use dev score
        if refold.get("iptm") is not None:
            iptm_norm = min(1.0, float(refold["iptm"]) / 0.9)   # 0.9 = excellent
            combined  = round(0.50 * iptm_norm + 0.50 * r.get("developability_score", 0.5), 4)
            struct_passed = refold.get("passes", False)
        else:
            combined      = r.get("developability_score", 0.0)
            struct_passed = r.get("passes", False)

        cand = {
            "id": f"BIO_{symbol}_{i+1:03d}",
            "sequence": seq,
            "length": len(seq),
            "type": "cyclic_peptide" if interface_ctx["cyclic_preferred"] else "linear_peptide",
            "design_strategy": interface_ctx["design_strategy"],
            "target_class": interface_ctx["target_class"],
            # Structural validation (populated when API keys available)
            "iptm":          refold.get("iptm"),
            "pae_interface": refold.get("pae_interface"),
            "binder_plddt":  refold.get("binder_plddt"),
            "refolding_source": refold.get("source"),
            # Developability
            "aggregation":        r.get("aggregation"),
            "solubility_score":   r.get("solubility_score"),
            "immunogenicity":     r.get("immunogenicity"),
            "n_mhc_strong_binders": r.get("n_mhc_strong_binders"),
            "developability_score": r.get("developability_score"),
            "stability":          r.get("stability", {}),
            "disqualifying":      r.get("disqualifying", []),
            "concerns":           r.get("concerns", []),
            "passed":             struct_passed,
            "combined_pre8":      combined,
            "rank": i + 1,
        }
        candidates.append(cand)

    # ── 6.4 LLM gate: immunogenicity report for top candidates ───────────────
    for c in candidates[:3]:
        try:
            c["immunogenicity_report"] = _gate_immunogenicity(
                provider=provider, db=db, run_id=run_id,
                symbol=symbol, candidate=c, config=config,
            )
        except Exception as exc:
            log.debug("[6.4] LLM immunogenicity gate skipped: %s", exc)
            c["immunogenicity_report"] = ""

    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# LLM gates
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> Optional[Dict]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 6.3 Refolding validation
# ─────────────────────────────────────────────────────────────────────────────

def _run_refolding_validation(
    *,
    sequences: List[str],
    pdb_url: str,
    neurosnap_key: str,
    nim_key: str,
    provider,
    db,
    run_id: str,
    symbol: str,
) -> tuple[List[str], Dict[str, Dict]]:
    """
    Refold each candidate sequence against the target PDB via Boltz-2 or AF2 NIM.

    Returns:
      (filtered_sequences, refolding_results_by_seq)
      filtered_sequences = passed (ipTM>0.7) + borderline after LLM triage
    """
    refolding: Dict[str, Dict] = {}

    for seq in sequences:
        result = None
        if neurosnap_key:
            try:
                from .neurosnap_boltzgen import score_refolding
                result = score_refolding(pdb_url, seq, api_key=neurosnap_key)
            except Exception as exc:
                log.debug("[6.3] Boltz-2 refolding failed for seq: %s", exc)

        if result is None and nim_key:
            try:
                from .nim_rfdiffusion import score_af2_nim
                result = score_af2_nim(pdb_url, seq, api_key=nim_key)
            except Exception as exc:
                log.debug("[6.3] AF2 NIM refolding failed for seq: %s", exc)

        if result:
            refolding[seq] = result

    if not refolding:
        # No refolding results — return all sequences unfiltered
        return sequences, {}

    passed     = [s for s in sequences if refolding.get(s, {}).get("passes")]
    borderline = [s for s in sequences
                  if s in refolding
                  and not refolding[s].get("passes")
                  and refolding[s].get("iptm", 0) >= 0.65]
    rejected   = [s for s in sequences
                  if s in refolding and s not in passed and s not in borderline]

    log.info("[6.3] %s refolding: %d passed / %d borderline / %d rejected",
             symbol, len(passed), len(borderline), len(rejected))

    # LLM gate 6.3: triage borderline sequences
    promoted = []
    if borderline:
        promoted = _gate_borderline_triage(
            provider=provider, db=db, run_id=run_id,
            symbol=symbol, borderline=borderline, refolding=refolding,
        )

    # Sequences that made it through: passed + promoted + unscored (no API result)
    unscored = [s for s in sequences if s not in refolding]
    final = list(dict.fromkeys(passed + promoted + unscored))  # preserve order, dedupe
    return final, refolding


def _gate_borderline_triage(
    *, provider, db, run_id: str, symbol: str,
    borderline: List[str], refolding: Dict[str, Dict],
) -> List[str]:
    """
    LLM gate 6.3: rank borderline ipTM (0.65–0.75) designs and promote top 1–2.
    Returns list of sequences to promote.
    """
    candidates_info = [
        {
            "sequence": seq,
            "iptm":          refolding[seq].get("iptm"),
            "pae_interface": refolding[seq].get("pae_interface"),
            "binder_plddt":  refolding[seq].get("binder_plddt"),
        }
        for seq in borderline[:5]   # max 5 borderline to triage
    ]
    prompt = (
        f"You are a structural biologist reviewing borderline protein-binder designs.\n\n"
        f"Target: {symbol}\n"
        f"These designs have borderline ipTM (0.65–0.75) — below the 0.7 pass threshold.\n\n"
        f"Borderline candidates:\n"
        + "\n".join(
            f"  {i+1}. seq={c['sequence'][:20]}... "
            f"ipTM={c['iptm']}, pAE={c['pae_interface']}, pLDDT={c['binder_plddt']}"
            for i, c in enumerate(candidates_info)
        )
        + f"\n\nPromote the top 1–2 most promising based on pAE_interface and pLDDT. "
        f"A low pAE_interface (<12) or high pLDDT (>75) can partially compensate for borderline ipTM.\n\n"
        f'Return ONLY: {{"promoted": [1, 2], "reasoning": "..."}}'
    )
    try:
        result = provider.complete(prompt, temperature=0.15, max_tokens=4000)
        parsed = _extract_json(result.text)
        run_state.log_decision(
            db, run_id=run_id, phase=6, gate=f"6.3_borderline_triage_{symbol}",
            provider=provider.name, model=getattr(provider, "model", "unknown"),
            prompt=prompt, raw_response=result.text, decision_json=parsed or {},
        )
        if parsed and "promoted" in parsed:
            indices = [int(i) - 1 for i in parsed["promoted"]
                       if isinstance(i, int) and 1 <= int(i) <= len(borderline)]
            return [borderline[i] for i in indices if i < len(borderline)]
    except Exception as exc:
        log.debug("[6.3] Borderline triage gate failed: %s", exc)
    # Fallback: promote top 1 by ipTM
    best = max(borderline, key=lambda s: refolding.get(s, {}).get("iptm", 0), default=None)
    return [best] if best else []


def _gate_hotspot_selection(
    *, provider, db, run_id: str, symbol: str, interface_ctx: Dict,
) -> List[str]:
    known_hotspots = interface_ctx.get("hotspots", [])
    pocket = interface_ctx.get("pocket", {})
    prompt = (
        f"You are a structural biologist selecting binding hotspots for peptide design.\n\n"
        f"Target: {symbol}\n"
        f"Target class: {interface_ctx.get('target_class')}\n"
        f"Pocket volume: {pocket.get('volume', 'unknown')} Å³\n"
        f"Druggability score: {pocket.get('druggability', 'unknown')}\n"
        f"Known pathogenic missense hotspots: {known_hotspots}\n\n"
        f"Select 3–5 hotspot residues (format: AA+position, e.g. R175, G12) "
        f"that would be most important to target for a peptide binder. "
        f"Prioritise interface-forming, catalytic, or allosteric residues.\n\n"
        f'Return ONLY: {{"hotspots": ["R175", "G12"], "reasoning": "...", '
        f'"design_strategy": "..."}}'
    )
    try:
        result = provider.complete(prompt, temperature=0.2, max_tokens=4000)
        parsed = _extract_json(result.text)
        run_state.log_decision(
            db, run_id=run_id, phase=6,
            gate=f"6.1_hotspot_{symbol}",
            provider=provider.name,
            model=getattr(provider, "model", "unknown"),
            prompt=prompt, raw_response=result.text,
            decision_json=parsed or {},
        )
        if parsed and "hotspots" in parsed:
            return parsed["hotspots"]
    except Exception as exc:
        log.debug("[6.1] hotspot gate failed: %s", exc)
    return known_hotspots


def _gate_immunogenicity(
    *, provider, db, run_id: str, symbol: str, candidate: Dict, config: RunConfig,
) -> str:
    prompt = (
        f"You are a biologic drug safety expert.\n\n"
        f"Target: {symbol}\n"
        f"Indication: {config.indication_type}\n"
        f"Peptide sequence: {candidate['sequence']}\n"
        f"Length: {candidate['length']} aa\n"
        f"Predicted MHC-II strong binders: {candidate.get('n_mhc_strong_binders', 0)}\n"
        f"Immunogenicity risk: {candidate.get('immunogenicity', 'unknown')}\n"
        f"Route of administration: {'systemic' if config.indication_type != 'acute' else 'acute/topical'}\n\n"
        f"Assess immunogenicity acceptability. "
        f"Is this acceptable for the indication? What de-immunization modifications would help?\n\n"
        f'Return ONLY: {{"acceptable": true, "risk_level": "low", '
        f'"recommendations": ["..."], "deimmunization_priority": "low"}}'
    )
    try:
        result = provider.complete(prompt, temperature=0.15, max_tokens=4000)
        parsed = _extract_json(result.text)
        run_state.log_decision(
            db, run_id=run_id, phase=6,
            gate=f"6.5_immunogenicity_{symbol}_{candidate['id']}",
            provider=provider.name,
            model=getattr(provider, "model", "unknown"),
            prompt=prompt, raw_response=result.text,
            decision_json=parsed or {},
        )
        if parsed:
            return (
                f"Acceptable: {parsed.get('acceptable')}. "
                f"Risk: {parsed.get('risk_level')}. "
                f"Recommendations: {'; '.join(parsed.get('recommendations', []))}"
            )
    except Exception as exc:
        log.debug("[6.5] immunogenicity gate failed: %s", exc)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Persistence + helpers
# ─────────────────────────────────────────────────────────────────────────────

def _persist_candidates(db, run_id: str, symbol: str, candidates: List[Dict]) -> None:
    for c in candidates:
        try:
            run_state.insert_candidate(
                db, run_id=run_id, symbol=symbol, phase=6,
                kind="biologic",
                candidate_id=c["id"],
                name=c["id"],
                smiles="",    # peptides don't have SMILES in this pipeline
                score=c.get("combined_pre8", 0.0),
                rank=c.get("rank", 0),
                passed=c.get("passed", False),
                evidence={
                    "sequence": c.get("sequence"),
                    "length": c.get("length"),
                    "type": c.get("type"),
                    "developability_score": c.get("developability_score"),
                    "aggregation": c.get("aggregation"),
                    "solubility_score": c.get("solubility_score"),
                    "immunogenicity": c.get("immunogenicity"),
                    "disqualifying": c.get("disqualifying", []),
                    "concerns": c.get("concerns", []),
                    "immunogenicity_report": c.get("immunogenicity_report", ""),
                },
            )
        except Exception as exc:
            log.warning("[6] DB persist failed for %s/%s: %s", symbol, c.get("id"), exc)


def _make_provider(config: RunConfig):
    from src.llm.factory import make_provider
    return make_provider(config.llm)


def _empty_output(t_start: float) -> Dict:
    return {
        "biologic": {},
        "n_targets": 0,
        "n_candidates_total": 0,
        "note": "No targets routed to P6 or de_novo_enabled=False",
        "wall_time_s": round(time.monotonic() - t_start, 1),
    }
