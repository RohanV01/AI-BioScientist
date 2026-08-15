"""
Kick off a real end-to-end run: bootstrap DB records → Phase 0 → Phase 1 → Phase 2 → Phase 3.
Runs inline (no Celery) so you can watch progress live.

Usage:
    # Full E2E through Phase 3 (default)
    python scripts/kickoff.py --disease "pancreatic cancer" --through 3

    # Phase 1 only (fast, ~50s)
    python scripts/kickoff.py --disease "pancreatic cancer" --through 1

    # Breast cancer
    python scripts/kickoff.py --disease "breast cancer" --through 3
"""
import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("kickoff")

from src.config.run_config import RunConfig, LLMConfig
from src.db.supabase_client import get_service_client
from src.phases.phase0.runner import run_phase0
from src.phases.phase1.runner import run_phase1

# ── Known positives for common diseases ──────────────────────────────────────
_KNOWN_POSITIVES = {
    "pancreatic cancer":    ["KRAS", "TP53", "SMAD4", "CDKN2A", "BRCA2"],
    "breast cancer":        ["BRCA1", "BRCA2", "TP53", "PIK3CA", "ERBB2"],
    "parkinson's disease":  ["LRRK2", "SNCA", "PINK1", "PRKN", "GBA"],
    "lung cancer":          ["KRAS", "EGFR", "TP53", "STK11", "KEAP1"],
    "colorectal cancer":    ["APC", "KRAS", "TP53", "BRAF", "PIK3CA"],
}


def bootstrap_run(db, config: RunConfig) -> str:
    """Create auth user → profile → project → run. Returns run_id."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    email = f"kickoff-{stamp}@local.test"

    user_resp = db.auth.admin.create_user({
        "email": email,
        "password": f"pw-{stamp}-x9",
        "email_confirm": True,
    })
    user_id = user_resp.user.id
    log.info("Created auth user %s", user_id)

    db.table("profiles").insert({"id": user_id, "email": email, "org": "Nurix"}).execute()

    proj = db.table("projects").insert({"owner_id": user_id, "name": "Kickoff"}).execute()
    project_id = proj.data[0]["id"]

    run = db.table("runs").insert({
        "project_id": project_id,
        "owner_id": user_id,
        "disease_name": config.disease_name,
        "config": config.model_dump(mode="json"),
        "intent_mode": config.intent_mode,
        "dry_run": False,
        "status": "pending",
    }).execute()
    run_id = run.data[0]["id"]
    log.info("Created run %s for '%s'", run_id, config.disease_name)
    return run_id


def _sep(title: str) -> None:
    print(f"\n{'='*60}\n{title}\n{'='*60}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--disease", default="pancreatic cancer")
    parser.add_argument("--provider", default="lmstudio",
                        choices=["lmstudio", "anthropic", "openai"])
    parser.add_argument("--targets", type=int, default=20)
    parser.add_argument("--through", type=int, default=3,
                        help="Highest phase to run (1=P1 only, 2=P1+P2, 3=P1+P2+P3)")
    parser.add_argument("--indication", default="oncology",
                        choices=["oncology", "chronic", "acute"])
    parser.add_argument("--tissue", default="Pancreas",
                        help="Tissue of interest for Phase 2 expression lookup")
    args = parser.parse_args()

    # Resolve known positives
    disease_key = args.disease.lower()
    known_positives = _KNOWN_POSITIVES.get(disease_key, [])
    if not known_positives:
        # Try partial match
        for k, v in _KNOWN_POSITIVES.items():
            if k in disease_key or disease_key in k:
                known_positives = v
                break
    if not known_positives:
        log.warning("No known positives found for '%s' — PU model will run with 0 positives", args.disease)

    config = RunConfig(
        disease_name=args.disease,
        intent_mode="explore",
        target_count_max=args.targets,
        known_positives=known_positives,
        indication_type=args.indication,
        tissue_of_interest=args.tissue,
        llm=LLMConfig(provider=args.provider),
    )

    log.info("Known positives: %s", known_positives)

    db = get_service_client()
    run_id = bootstrap_run(db, config)

    # ── Phase 0 ───────────────────────────────────────────────────────────────
    _sep("PHASE 0: health checks")
    p0 = run_phase0(run_id=run_id, config=config, db=db)
    print(f"Verdict: {p0['go_no_go']}  (cost est ${p0['cost_estimate_usd']})")
    if p0.get("go_no_go") != "go":
        print(f"Blocked by: {p0.get('missing_required', [])}")
        return

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    _sep("PHASE 1: target identification (tabular PU-learning)")
    p1 = run_phase1(run_id=run_id, config=config, db=db, phase0_output=p0)

    model = p1.get("model", {})
    print(f"EFO:        {p1['efo_id']}  ({p1.get('disease_label')})")
    print(f"Method:     {model.get('method')}  estimator={model.get('estimator')}")
    print(f"Positives:  {model.get('n_positives')}  genes={model.get('n_genes')}")
    print(f"AUROC(LOO): {model.get('auroc_loo')}")
    print(f"Wall time:  {p1['wall_time_s']}s")
    print(f"\nTop-10 ranked targets:")
    for t in p1["ranked_targets"][:10]:
        trail = t.get("evidence_trail", {})
        flags = " [SEED]" if t["seeded"] else ""
        print(f"  {t['rank']:2d}. {t['symbol']:12s}  score={t['aggregate_score']:.4f}"
              f"  tract={trail.get('tractability',0):.2f}"
              f"  genetic={trail.get('genetic',0):.3f}{flags}")

    if args.through < 2:
        print(f"\nRun ID: {run_id}")
        return

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    _sep("PHASE 2: target validation (structure · pockets · essentiality · expression)")
    from src.phases.phase2.runner import run_phase2
    p2 = run_phase2(run_id=run_id, config=config, db=db, phase1_output=p1)

    print(f"Validated: {p2['n_passing']}/{p2['n_total']} targets  "
          f"(threshold={p2['threshold_used']}  wall_time={p2['wall_time_s']}s)")
    print(f"\nValidated targets:")
    for t in p2["validated_targets"]:
        mod = t.get("modality", {})
        ess = t.get("essentiality", {})
        var = t.get("variants", {})
        print(f"  {t['symbol']:12s}  val={t['validation_score']:.3f}"
              f"  primary={mod.get('primary','?'):8s}"
              f"  chronos={ess.get('chronos','N/A')}"
              f"  am_frac={var.get('am_high_path_fraction',0):.2f}"
              f"  pLDDT={t.get('structure',{}).get('median_plddt',0):.0f}")

    if args.through < 3:
        print(f"\nRun ID: {run_id}")
        return

    # ── Phase 3 ───────────────────────────────────────────────────────────────
    _sep("PHASE 3: modality routing")
    from src.phases.phase3.runner import run_phase3
    p3 = run_phase3(run_id=run_id, config=config, db=db, phase2_output=p2)

    print(f"Routed {len(p3['routing'])} targets  (intent_mode={p3['intent_mode']}  "
          f"wall_time={p3['wall_time_s']}s)")
    print(f"\nRouting table:")
    for r in p3["routing"]:
        print(f"  {r['symbol']:12s}  primary={r['primary']:20s}"
              f"  priority={r['repurposing_priority']:12s}"
              f"  branches={r['branches']}")

    _sep("COMPLETE")
    print(f"Run ID:  {run_id}")
    print(f"Disease: {config.disease_name}")
    print(f"Phases:  0 → {args.through} complete")
    print(f"\nView in studio: http://localhost:5173")


if __name__ == "__main__":
    main()
