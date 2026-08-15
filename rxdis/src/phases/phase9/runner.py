"""
Phase 9 — Output Packaging & Reproducibility runner.

Steps:
  9.1  Assemble directory tree from all phase outputs + DB tables
  9.2  LLM self-audit: check attrition counts, cost reasonableness, flag anomalies
  9.3  LLM executive summary: write README.md
  9.4  Zip + upload to Supabase Storage
  9.5  Mark run completed with cost_actual and package_path
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config.run_config import RunConfig
from src.db import run_state

from .assembler import assemble_package, upload_package, zip_package, _collect_version_pins

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_phase9(
    run_id: str,
    config: RunConfig,
    db,
    phase1_output: Optional[Dict] = None,
    phase2_output: Optional[Dict] = None,
    phase3_output: Optional[Dict] = None,
    phase4_output: Optional[Dict] = None,
    phase5_output: Optional[Dict] = None,
    phase6_output: Optional[Dict] = None,
    phase7_output: Optional[Dict] = None,
    phase8_output: Optional[Dict] = None,
) -> Dict[str, Any]:
    from src.phases.base_runner import PhaseGuard
    t_start = time.monotonic()
    # Phase 9 (packaging) occupies DB slot phase=8 per the schema design
    with PhaseGuard(db, run_id, phase=8, config=config) as guard:
        guard.check_budget()
        return _run_phase9_body(
            run_id=run_id, config=config, db=db,
            phase1_output=phase1_output, phase2_output=phase2_output,
            phase3_output=phase3_output, phase4_output=phase4_output,
            phase5_output=phase5_output, phase6_output=phase6_output,
            phase7_output=phase7_output, phase8_output=phase8_output,
            t_start=t_start,
        )


def _run_phase9_body(
    run_id: str, config: RunConfig, db,
    phase1_output: Optional[Dict], phase2_output: Optional[Dict],
    phase3_output: Optional[Dict], phase4_output: Optional[Dict],
    phase5_output: Optional[Dict], phase6_output: Optional[Dict],
    phase7_output: Optional[Dict], phase8_output: Optional[Dict],
    t_start: float,
) -> Dict[str, Any]:
    provider = _make_provider(config)

    all_phase_outputs = {
        "phase1": phase1_output,
        "phase2": phase2_output,
        "phase3": phase3_output,
        "phase4": phase4_output,
        "phase5": phase5_output,
        "phase6": phase6_output,
        "phase7": phase7_output,
        "phase8": phase8_output,
    }

    # ── 9.1 Assemble package ─────────────────────────────────────────────────
    log.info("[Phase 9] Assembling output package…")
    package_root = assemble_package(
        run_id=run_id,
        config=config,
        db=db,
        all_phase_outputs=all_phase_outputs,
        output_base_dir=config.output_dir,
    )

    # ── 9.2 LLM self-audit ──────────────────────────────────────────────────
    audit = _gate_self_audit(
        provider=provider, db=db, run_id=run_id,
        config=config, all_phase_outputs=all_phase_outputs,
    )
    log.info("[9.2] Self-audit passed=%s concerns=%d",
             audit.get("audit_passed"), len(audit.get("concerns", [])))

    # ── 9.3 LLM executive summary ────────────────────────────────────────────
    readme_md = _gate_executive_summary(
        provider=provider, db=db, run_id=run_id,
        config=config, all_phase_outputs=all_phase_outputs,
        audit=audit,
    )
    (package_root / "README.md").write_text(readme_md)

    # ── 9.4 Zip + upload ────────────────────────────────────────────────────
    zip_path = zip_package(package_root)
    package_url = upload_package(zip_path, run_id, db)

    # Cost estimate from compute_log
    cost_actual = _estimate_cost(db, run_id)

    # ── 9.5 Finalise ────────────────────────────────────────────────────────
    try:
        db.table("runs").update({
            "status": "completed",
            "cost_actual": cost_actual,
            "updated_at": _now(),
        }).eq("id", run_id).execute()
    except Exception as exc:
        log.warning("[9] DB run finalise failed: %s", exc)

    wall_time = round(time.monotonic() - t_start, 1)

    # Count totals
    n_targets = len((phase1_output or {}).get("ranked_targets", []))
    n_candidates = (
        len((phase8_output or {}).get("validation", {}))
        + sum(
            len(c) for c in (phase4_output or {}).get("repurposing", {}).values()
        )
    )

    output = {
        "package_path": str(zip_path),
        "package_url": package_url,
        "ranked_targets_count": n_targets,
        "candidates_total": n_candidates,
        "cost_actual_usd": cost_actual,
        "audit": audit,
        "reproducibility": _collect_version_pins(),
        "wall_time_s": wall_time,
    }

    run_state.mark_phase_completed(db, run_id, phase=8, output=output)
    run_state.log_compute(db, run_id=run_id, phase=8, step="phase8_complete",
                          service="local", wall_time_s=wall_time)
    log.info("[Phase 8] Complete. Package: %s (%.1fs)", package_url or str(zip_path), wall_time)
    return output


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


def _gate_self_audit(
    *, provider, db, run_id: str, config: RunConfig, all_phase_outputs: Dict,
) -> Dict:
    p1 = all_phase_outputs.get("phase1") or {}
    p2 = all_phase_outputs.get("phase2") or {}
    p4 = all_phase_outputs.get("phase4") or {}
    p8 = all_phase_outputs.get("phase8") or {}

    n_targets_p1   = len(p1.get("ranked_targets", []))
    n_targets_p2   = p2.get("n_passing", 0)
    n_candidates_p4 = p4.get("n_candidates_total", 0)
    n_passed_p8    = p8.get("n_candidates_passed", 0)

    prompt = (
        f"You are auditing a computational drug discovery run for quality.\n\n"
        f"Disease: {config.disease_name}\n"
        f"Intent: {config.intent_mode}\n\n"
        f"Attrition funnel:\n"
        f"  Phase 1 targets ranked: {n_targets_p1}\n"
        f"  Phase 2 targets validated: {n_targets_p2}\n"
        f"  Phase 4 repurposing candidates: {n_candidates_p4}\n"
        f"  Phase 8 candidates passed: {n_passed_p8}\n\n"
        f"Check for:\n"
        f"  1. Unreasonable attrition (e.g. 20 targets → 0 candidates)\n"
        f"  2. Unexpected zero counts at any phase\n"
        f"  3. Cost or time anomalies\n"
        f"  4. Caveats to include in the final report\n\n"
        f"Is this run trustworthy? Provide concerns and caveats for the report.\n\n"
        f'Return ONLY: {{"audit_passed": true, "concerns": [], '
        f'"caveats_for_report": ["..."], "recommended_rerun": false}}'
    )

    audit_result = {
        "audit_passed": True,
        "concerns": [],
        "caveats_for_report": [],
        "recommended_rerun": False,
    }
    try:
        result = provider.complete(prompt, temperature=0.15, max_tokens=400)
        parsed = _extract_json(result.text)
        if parsed:
            audit_result.update(parsed)
        run_state.log_decision(
            db, run_id=run_id, phase=8, gate="8_self_audit",
            provider=provider.name,
            model=getattr(provider, "model", "unknown"),
            prompt=prompt, raw_response=result.text,
            decision_json=audit_result,
        )
    except Exception as exc:
        log.debug("[9.2] Self-audit gate failed: %s", exc)
        audit_result["concerns"].append(f"self_audit_gate_error: {exc}")

    # Hard-code sanity check: zero targets → flag
    if n_targets_p1 == 0:
        audit_result["audit_passed"] = False
        audit_result["concerns"].append("Phase 1 returned zero targets")

    return audit_result


def _gate_executive_summary(
    *, provider, db, run_id: str, config: RunConfig,
    all_phase_outputs: Dict, audit: Dict,
) -> str:
    p1 = all_phase_outputs.get("phase1") or {}
    p8 = all_phase_outputs.get("phase8") or {}

    top_targets = [t["symbol"] for t in p1.get("ranked_targets", [])[:5]]
    passed_candidates = p8.get("n_candidates_passed", 0)
    caveats = audit.get("caveats_for_report", [])

    prompt = (
        f"Write a README.md executive summary for a computational drug discovery run.\n\n"
        f"Disease: {config.disease_name} ({config.disease_efo_id or 'EFO unknown'})\n"
        f"Intent mode: {config.intent_mode}\n"
        f"Top targets identified: {top_targets}\n"
        f"Final validated candidates: {passed_candidates}\n"
        f"Caveats from audit: {caveats}\n\n"
        f"Write in Markdown. Include:\n"
        f"  - H2: Overview (disease, pipeline, intent)\n"
        f"  - H2: Top Targets (bullet list)\n"
        f"  - H2: Key Findings (candidates, confidence)\n"
        f"  - H2: Caveats & Limitations\n"
        f"  - H2: Reproducibility (how to re-run)\n\n"
        f'Return ONLY: {{"readme_markdown": "# ..."}}'
    )

    default_readme = _default_readme(config, top_targets, passed_candidates, caveats)
    try:
        result = provider.complete(prompt, temperature=0.3, max_tokens=800)
        parsed = _extract_json(result.text)
        run_state.log_decision(
            db, run_id=run_id, phase=8, gate="8_executive_summary",
            provider=provider.name,
            model=getattr(provider, "model", "unknown"),
            prompt=prompt, raw_response=result.text,
            decision_json=parsed or {},
        )
        if parsed and "readme_markdown" in parsed:
            return str(parsed["readme_markdown"])
    except Exception as exc:
        log.debug("[9.3] Executive summary gate failed: %s", exc)

    return default_readme


def _default_readme(
    config, top_targets: List[str], n_candidates: int, caveats: List[str],
) -> str:
    return f"""# RxDis Run — {config.disease_name}

## Overview
Disease: **{config.disease_name}** | Intent: `{config.intent_mode}` | Indication: `{config.indication_type}`

This package contains the full output of an automated in-silico drug discovery run
using the BioCatalyst Lab pipeline (Phases 0–8).

## Top Targets
{chr(10).join(f'- {t}' for t in top_targets) or '- (none identified)'}

## Key Findings
- Final validated candidates: **{n_candidates}**
- See `targets/{{symbol}}/` for per-target evidence, candidates, and ADMET data.
- See `decisions.json` for all LLM gate decisions and reasoning.

## Caveats & Limitations
{chr(10).join(f'- {c}' for c in caveats) or '- No critical caveats.'}
- Binding confirmed by triple Vina re-dock (exhaustiveness=12); no MD simulation.
- Biologic candidates scored by developability; Boltz-2 refolding available locally.

## Reproducibility
See `run_metadata.json` for exact DB versions and config.
Re-run with:
```
python scripts/kickoff.py --disease "{config.disease_name}" --intent {config.intent_mode}
```
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _estimate_cost(db, run_id: str) -> float:
    """Sum cost_usd from compute_log for this run."""
    try:
        resp = db.table("compute_log").select("cost_usd").eq("run_id", run_id).execute()
        return round(sum(r.get("cost_usd", 0.0) for r in (resp.data or [])), 4)
    except Exception:
        return 0.0


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _make_provider(config: RunConfig):
    from src.llm.factory import make_provider
    return make_provider(config.llm)
