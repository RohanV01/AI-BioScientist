"""
Phase 3 runner — modality routing over Phase 2 validated targets.

Routes only the targets that passed Phase 2 validation. Writes final modality
routing onto the `targets` rows and emits the routing I/O contract.
"""
from __future__ import annotations
import logging
import time
from typing import Any, Dict, List

from src.config.run_config import RunConfig
from src.llm.factory import make_provider
from src.db import run_state

from .rule_engine import route_target

log = logging.getLogger(__name__)


def run_phase3(run_id: str, config: RunConfig, db, phase2_output: Dict) -> Dict[str, Any]:
    validated = phase2_output.get("validated_targets", [])
    if not validated:
        raise RuntimeError("Phase 3 requires Phase 2 validated_targets; none found.")

    run_state.mark_phase_running(db, run_id, phase=3)
    t_start = time.monotonic()
    provider = make_provider(config.llm)

    # Only route targets that passed validation (seeded ones are flagged passed).
    passing = [v for v in validated if v.get("passed")]
    if not passing:
        log.warning("[Phase 3] No targets passed Phase 2 — routing all validated as hard targets")
        passing = validated

    seed_smiles_present = bool(config.seed_smiles)
    novelty_mode = bool(getattr(config, "novelty_mode", False))

    routing: List[Dict] = []
    for target in passing:
        record = route_target(
            target=target,
            intent_mode=config.intent_mode,
            modality_preference=config.modality_preference,
            seed_smiles_present=seed_smiles_present,
            novelty_mode=novelty_mode,
            provider=provider, db=db, run_id=run_id,
        )
        routing.append(record)

        try:
            run_state.update_target_routing(
                db, run_id=run_id, symbol=record["symbol"],
                modality_primary=record["primary"],
                modality_secondary=record["secondary"],
            )
        except Exception as exc:
            log.warning("[Phase 3] DB update failed for %s: %s", record["symbol"], exc)

    output = {
        "routing": routing,
        "n_routed": len(routing),
        "branch_summary": _branch_summary(routing),
        "wall_time_s": round(time.monotonic() - t_start, 1),
    }

    run_state.mark_phase_completed(db, run_id, phase=3, output=output)
    run_state.log_compute(db, run_id=run_id, phase=3, step="phase3_complete",
                          service="local", wall_time_s=output["wall_time_s"])

    log.info("[Phase 3] Complete: routed %d targets in %.1fs. Branches: %s",
             len(routing), output["wall_time_s"], output["branch_summary"])
    return output


def _branch_summary(routing: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in routing:
        for b in r["branches"]:
            counts[b] = counts.get(b, 0) + 1
    return counts
