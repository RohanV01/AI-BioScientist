# Regression Checklist

Run this after every significant code change before merging. Covers all previous fix points.

---

## Smoke Test (< 5 min)

Run these every time, in order.

```
[ ] GET /api/health → 200, all_ok: true
[ ] POST /api/runs with standard fixture → 200 (not 422)
[ ] Standard fixture: { disease: "pancreatic cancer", known_positives: ["KRAS","TP53","SMAD4","CDKN2A","BRCA2"], indication_type: "oncology", provider: "lmstudio", pu_n_bags: 30 }
[ ] UI loads without white screen
[ ] No red JS errors in DevTools Console on home page
[ ] Indication dropdown shows exactly: oncology, chronic, acute
[ ] Provider dropdown shows exactly: lmstudio, anthropic, openai
[ ] TypeScript: npx tsc --noEmit → 0 errors
```

---

## Fix Regression Tests

Verify each previous fix has not regressed.

### BUG-F01/F02 — 422 Regression
```
[ ] POST /api/runs with provider: "lmstudio" + indication_type: "oncology" → 200
[ ] POST /api/runs with provider: "lmstudio" + indication_type: "chronic" → 200
[ ] POST /api/runs with provider: "lmstudio" + indication_type: "acute" → 200
[ ] POST /api/runs with provider: "local" → 422 (expected)
[ ] POST /api/runs with indication_type: "neurology" → 422 (expected)
```

### BUG-F03/F04 — IMPLEMENTED_MAX Regression
```
[ ] Open any run in RunCanvas
[ ] Phase 5 card is NOT greyed out
[ ] Phase 6 card is NOT greyed out  
[ ] Phase 7 card is NOT greyed out
[ ] Phase 8 card is NOT greyed out
[ ] Phase 9 card is NOT greyed out
[ ] Click Phase 5 "View →" → opens phase view (not disabled)
```

### BUG-F05 — Auto-Jump Regression
```
[ ] Open a completed run from sidebar
[ ] Verify: lands on phase grid overview (all 10 cards visible)
[ ] Verify: does NOT immediately show Phase 1 target list
```

### BUG-F06 — xgb_probability Regression
```
[ ] Run Phase 1 (or open existing completed run)
[ ] Open any known-positive target (KRAS, TP53, etc.)
[ ] Verify "★" (star) icon is visible in target row
[ ] Verify PU score column shows decimal number (not blank)
[ ] In DB: evidence_trail.xgb_probability is non-null
```

### BUG-F07 — Sidebar RunRow Click Regression
```
[ ] Open app, run exists in DB
[ ] Click module run row in sidebar
[ ] Verify: navigates to that run's RunCanvas
[ ] Verify: no console error on click
```

### BUG-F08 — pu_n_bags Regression
```
[ ] Launch a new run
[ ] Check network request body in DevTools
[ ] Verify: pu_n_bags = 30 in POST body (not 10 or 5)
[ ] Alternatively: check phase_results.output_json.n_bags = 30 after Phase 1
```

---

## Full Phase Regression (run after major refactors)

These are slow — only run on major structural changes.

```
Phase 0:
[ ] DB seeded (known_positives in targets table with seeded evidence)

Phase 1:
[ ] ≥ 10 targets with pu_bio_score > 0
[ ] ≥ 5 known positives in top 50 by score
[ ] AUROC reported in phase_results.output_json

Phase 2:
[ ] All top-N targets have evidence_trail.phase2 block
[ ] passed/failed boolean on each

Phase 3:
[ ] All Phase 2 passed targets have evidence_trail.phase3 block
[ ] modality_primary ≠ "unknown"

Phase 4 (repurposing):
[ ] ≥ 1 candidate with kind="repurposing"

Phase 5 (de novo SM):
[ ] ≥ 1 candidate with kind="sm", smiles non-null

Phase 6 (biologic):
[ ] ≥ 1 candidate with kind="biologic", sequence non-null

Phase 7 (MPO):
[ ] ≥ 1 candidate with subscores.pareto_rank set

Phase 8 (validation):
[ ] ≥ 1 candidate with subscores.passed = true

Phase 9 (packaging):
[ ] audit_passed = true
[ ] package_path non-null
[ ] runs.status = "completed"
```

---

## TypeScript Regression

```bash
cd frontend && npx tsc --noEmit
```

Expected: `0 errors`

---

## After Each Deployment

```
[ ] Smoke test passes
[ ] No new 422 errors in backend logs
[ ] No new Supabase RLS policy errors in logs
[ ] All 10 phase cards clickable on a completed run
```
