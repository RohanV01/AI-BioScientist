"""
Kick off a real end-to-end run: bootstrap DB records → Phase 0 → Phase 1.
Runs inline (no Celery) so you can watch progress live.

Usage:
    python scripts/kickoff.py --disease "pancreatic cancer" --abstracts 40
"""
import argparse
import json
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("kickoff")

from src.config.run_config import RunConfig
from src.db.supabase_client import get_service_client
from src.phases.phase0.runner import run_phase0
from src.phases.phase1.runner import run_phase1
from src.phases.phase2.runner import run_phase2
from src.phases.phase3.runner import run_phase3


def bootstrap_run(db, config: RunConfig) -> str:
    """Create profile → project → run records. Returns run_id."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    email = f"kickoff-{stamp}@local.test"

    # 1. Auth user (service role can create directly)
    user_resp = db.auth.admin.create_user({
        "email": email,
        "password": f"pw-{stamp}-x9",
        "email_confirm": True,
    })
    user_id = user_resp.user.id
    log.info("Created auth user %s", user_id)

    # 2. Profile
    db.table("profiles").insert({"id": user_id, "email": email, "org": "Nurix"}).execute()

    # 3. Project
    proj = db.table("projects").insert({"owner_id": user_id, "name": "Kickoff"}).execute()
    project_id = proj.data[0]["id"]

    # 4. Run
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--disease", default="pancreatic cancer")
    parser.add_argument("--provider", default="lmstudio", choices=["lmstudio", "anthropic", "openai"])
    parser.add_argument("--abstracts", type=int, default=40,
                        help="Literature corpus cap (PRD default 500; lower = faster first run)")
    parser.add_argument("--targets", type=int, default=20)
    parser.add_argument("--through", type=int, default=1,
                        help="Highest phase to run (1=Phase 1 only, 3=through modality selection)")
    args = parser.parse_args()

    config = RunConfig(
        disease_name=args.disease,
        intent_mode="explore",
        target_count_max=args.targets,
        llm={"provider": args.provider},
    )

    db = get_service_client()
    run_id = bootstrap_run(db, config)

    print(f"\n{'='*60}\nPHASE 0: health checks\n{'='*60}")
    p0 = run_phase0(run_id=run_id, config=config, db=db)
    print(f"Phase 0 verdict: {p0['go_no_go']}  (cost est ${p0['cost_estimate_usd']})")
    if p0["go_no_go"] != "go":
        print(f"Blocked: {p0['missing_required']}")
        return

    print(f"\n{'='*60}\nPHASE 1: target identification "
          f"(corpus cap={args.abstracts})\n{'='*60}")
    p1 = run_phase1(run_id=run_id, config=config, db=db, phase0_output=p0,
                    lit_max_abstracts=args.abstracts)

    print(f"\n{'='*60}\nRESULTS\n{'='*60}")
    print(f"EFO: {p1['efo_id']}  ({p1.get('disease_label')})")
    print(f"Abstracts mined: {p1['abstract_count']}")
    print(f"Wall time: {p1['wall_time_s']}s")
    print(f"\nRanked targets:")
    for t in p1["ranked_targets"]:
        flags = []
        if t["seeded"]:
            flags.append("SEED")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        print(f"  {t['rank']:2d}. {t['symbol']:12s} score={t['aggregate_score']:.3f} "
              f"tdl={t['tdl']:6s} mod={t['modality_hint']}{flag_str}")

    p2 = p3 = None
    if args.through >= 2:
        print(f"\n{'='*60}\nPHASE 2: target validation\n{'='*60}")
        p2 = run_phase2(run_id=run_id, config=config, db=db, phase1_output=p1)
        print(f"Validated {p2['n_validated']} targets; "
              f"{p2['n_passed']} passed (threshold {p2['threshold_used']})")
        for v in p2["validated_targets"]:
            mark = "PASS" if v["passed"] else "drop"
            print(f"  [{mark}] {v['symbol']:12s} vscore={v['validation_score']:.3f} "
                  f"struct={v['structure']['source']:6s} "
                  f"drug={v['max_druggability']} mod={v['modality']['primary']}")

    if args.through >= 3 and p2 is not None:
        print(f"\n{'='*60}\nPHASE 3: modality selection\n{'='*60}")
        p3 = run_phase3(run_id=run_id, config=config, db=db, phase2_output=p2)
        for r in p3["routing"]:
            sec = f"/{r['secondary']}" if r["secondary"] else ""
            print(f"  {r['symbol']:12s} {r['primary']}{sec:10s} "
                  f"branches={r['branches']} repurpose={r['repurposing_priority']}")
        print(f"\nBranch summary: {p3['branch_summary']}")

    print(f"\nRun ID: {run_id}")
    print("Full output saved to phase_results table.")


if __name__ == "__main__":
    main()
