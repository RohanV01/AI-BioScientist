# Phase 7+8 — MPO Optimization + Validation Gate

---

## Phase 7 — Multi-Parameter Optimization (MPO Lab)

**Runner:** `src/phases/phase7/runner.py`
**Duration:** ~6 hours
**Depends on:** Phase 5 and/or Phase 6 output

### What it does
1. GP surrogate model fits on Phase 5+6 candidate scores
2. Bayesian optimization over drug-likeness axes (QED, SA, Vina, ADMET, selectivity, novelty)
3. Pareto front extraction (non-dominated solutions)
4. Outputs ranked Pareto-optimal candidates per target

### Expected Output JSON
```json
{
  "n_targets": 5,
  "n_pareto_total": 12,
  "wall_time_s": 21600.0
}
```

### DB State
**`candidates` table** — `subscores.pareto_rank` present on Pareto-optimal candidates

### API Assertions (Postman)
```javascript
pm.test("Phase 7 compute logged", () => {
  const p7 = pm.response.json().compute.find(c => c.phase === 7);
  pm.expect(p7).to.exist;
  pm.expect(p7.wall_time_s).to.be.above(0);
});
```

### UI Assertions
| Step | Action | Expected |
|------|--------|----------|
| 1 | Phase 7 card | "Completed", clickable |
| 2 | MPO Lab view | Pareto scatter plot or candidate table |
| 3 | "Stop early" button | Shows alert (BUG-005, known) |
| 4 | "Run more" button | Shows alert (BUG-005, known) |

### What "PASS" Means
- [ ] Phase 7 card "Completed"
- [ ] `n_pareto_total` ≥ 1
- [ ] At least one candidate has `pareto_rank` in subscores

---

## Phase 8 — Validation Gate

**Runner:** `src/phases/phase8/runner.py`
**Duration:** ~24h+ (triple Vina docking)
**Depends on:** Phase 7 (Pareto candidates) and/or Phase 4 (repurposing)

### What it does
1. Re-docks Pareto candidates with 3 Vina configurations (exhaustiveness 16/32/64)
2. MM-GBSA scoring (if configured)
3. Free energy perturbation (FEP, if configured)
4. Final pass/fail gate per candidate
5. Scorecard generation

### Expected Output JSON
```json
{
  "n_targets": 5,
  "n_candidates_passed": 8,
  "wall_time_s": 86400.0
}
```

### DB State
**`candidates` table**
| Column | Value |
|--------|-------|
| `subscores.passed` | true or false |
| `subscores.vina_triple` | array of 3 docking scores |
| `subscores.fail_reason` | string or null |

### API Assertions (Postman)
```javascript
pm.test("Phase 8 compute logged", () => {
  const p8 = pm.response.json().compute.find(c => c.phase === 8);
  pm.expect(p8).to.exist;
});
pm.test("At least 1 candidate passed", () => {
  // Check via Supabase or candidates endpoint when available
});
```

### UI Assertions
| Step | Action | Expected |
|------|--------|----------|
| 1 | Phase 8 card | "Completed", not greyed out ← fix verification |
| 2 | Validation Gate view | Candidate scorecard table |
| 3 | Pass/Fail badges | Green PASS / Red FAIL per candidate |
| 4 | Vina scores | Three columns (low/med/high exhaustiveness) |

### What "PASS" Means
- [ ] Phase 8 card "Completed" and clickable
- [ ] `n_candidates_passed` ≥ 1
- [ ] Each candidate has `subscores.passed` boolean
