"""Run Phase 2 → 3 → 4 on the pancreatic cancer run and save all results to Supabase."""
import sys, os, json, logging, time
sys.path.insert(0, '/home/rohanvyas/Documents/AI Scientist')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
log = logging.getLogger("run_p234")

with open('/home/rohanvyas/Documents/AI Scientist/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

from supabase import create_client
from src.config.run_config import RunConfig
from src.db.run_state import get_phase_output

db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
RUN_ID = "ba96b0c6-9027-4d70-8937-5629760ab40e"

run = db.table("runs").select("config").eq("id", RUN_ID).single().execute().data
config = RunConfig(**run["config"])
log.info("Config: disease=%s indication=%s targets=%d", config.disease_name, config.indication_type, config.target_count_max)

p1_output = get_phase_output(db, RUN_ID, phase=1)
log.info("P1: %d ranked targets loaded", len(p1_output.get("ranked_targets", [])))

# ── Phase 2 ────────────────────────────────────────────────────────────────
log.info("=" * 60)
log.info("STARTING PHASE 2 — Target Validation")
log.info("=" * 60)
t2 = time.monotonic()
from src.phases.phase2.runner import run_phase2
p2_output = run_phase2(run_id=RUN_ID, config=config, db=db, phase1_output=p1_output)
log.info("Phase 2 done: %d/%d passed  (%.1fs)", p2_output["n_passing"], p2_output["n_total"], time.monotonic() - t2)

# ── Phase 3 ────────────────────────────────────────────────────────────────
log.info("=" * 60)
log.info("STARTING PHASE 3 — Modality Routing")
log.info("=" * 60)
t3 = time.monotonic()
from src.phases.phase3.runner import run_phase3
p3_output = run_phase3(run_id=RUN_ID, config=config, db=db, phase2_output=p2_output)
repurpose = [r["symbol"] for r in p3_output["routing"] if "P4_repurpose" in r.get("branches", [])]
log.info("Phase 3 done: %d routed, P4 targets: %s  (%.1fs)", len(p3_output["routing"]), repurpose, time.monotonic() - t3)

# ── Phase 4 ────────────────────────────────────────────────────────────────
log.info("=" * 60)
log.info("STARTING PHASE 4 — Drug Repurposing (%d targets)", len(repurpose))
log.info("=" * 60)
t4 = time.monotonic()
from src.phases.phase4.runner import run_phase4
p4_output = run_phase4(
    run_id=RUN_ID, config=config, db=db,
    phase2_output=p2_output, phase3_output=p3_output, phase1_output=p1_output,
)
log.info("Phase 4 done: %d candidates, %d targets  (%.1fs)",
         p4_output["n_candidates_total"], p4_output["n_targets_screened"], time.monotonic() - t4)

# ── Print results ──────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("PIPELINE RESULTS — Pancreatic Cancer (EFO_0002618)")
print("=" * 70)
print(f"Phase 2: {p2_output['n_passing']}/{p2_output['n_total']} validated  ({p2_output['wall_time_s']:.0f}s)")
print(f"Phase 3: {len(p3_output['routing'])} routed → P4 targets: {repurpose}")
print(f"Phase 4: {p4_output['n_candidates_total']} candidates  ({p4_output['wall_time_s']:.0f}s)")
print()

for sym, hits in p4_output["repurposing"].items():
    cov = hits[0].get("is_covalent_target", False) if hits else False
    ceiling = hits[0].get("vina_ceiling_used", "?") if hits else "?"
    print(f"{'─'*70}")
    print(f"TARGET: {sym}  {'⚠ COVALENT TARGET' if cov else ''}  (Vina ceiling={ceiling} kcal/mol)")
    for c in hits[:5]:
        flags = []
        if c.get("lincs_dominant"):  flags.append("LINCS-dominant")
        if c.get("borderline"):      flags.append("borderline")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        print(f"  #{c['rank']:2d}  {c['drug_name']:22s}  "
              f"score={c['repurposing_score']:.3f}  pass={str(c['passed']):5s}  "
              f"mech={c['pass_mechanism']:14s}  "
              f"vina={str(c.get('vina_score') or 'N/A'):8s}  "
              f"kg={c.get('kg_score',0):.1f}  lincs={c.get('lincs_score',0):.2f}"
              f"{flag_str}")

# ── DB verification ────────────────────────────────────────────────────────
print(f"\n{'─'*70}")
candidates_in_db = db.table("candidates").select("id,target_symbol,score,passed,evidence").eq("run_id", RUN_ID).execute()
rows = candidates_in_db.data or []
print(f"Candidates saved to Supabase: {len(rows)}")
passed_count = sum(1 for r in rows if r.get("passed"))
print(f"  Passed: {passed_count}  |  Borderline: {len(rows) - passed_count}")
by_target = {}
for r in rows:
    by_target.setdefault(r["target_symbol"], []).append(r["score"])
for sym, scores in sorted(by_target.items()):
    print(f"  {sym}: {len(scores)} candidates, top score={max(scores):.3f}")
print("\nALL PHASES COMPLETE AND SAVED TO DB ✓")
