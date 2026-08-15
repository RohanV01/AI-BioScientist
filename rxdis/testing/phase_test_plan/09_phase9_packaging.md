# Phase 9 — Packaging & Report

**Runner:** `src/phases/phase9/runner.py` + `assembler.py`
**Duration:** ~5 minutes
**Depends on:** All prior phase outputs

---

## What Phase 9 Does

1. Assembles all phase outputs into a reproducibility-pinned package
2. Generates executive summary report
3. Creates ZIP archive with all artifacts
4. Pins all database versions, model weights, random seeds
5. Audit check (completeness, data integrity)
6. Writes `package_path` to DB

---

## Expected Output JSON

```json
{
  "package_path": "/output/run/pancreatic_cancer_2026-06-06/package.zip",
  "package_url": null,
  "candidates_total": 25,
  "cost_actual_usd": 0.0,
  "audit": {
    "audit_passed": true,
    "checks": ["targets_present", "candidates_present", "phases_complete"]
  },
  "wall_time_s": 180.0
}
```

---

## Expected DB State After

**Table: `runs`**
| Column | Value |
|--------|-------|
| `status` | `"completed"` |
| `current_phase` | `9` |
| `cost_actual` | number ≥ 0 |

**Table: `phase_results`** (phase=9)
| Column | Value |
|--------|-------|
| `status` | `"completed"` |
| `output_json.audit.audit_passed` | `true` |
| `output_json.package_path` | non-null string |

---

## API Assertions (Postman)

```javascript
// GET /api/runs/{run_id}
pm.test("Run fully completed", () => {
  pm.expect(pm.response.json().run.status).to.equal('completed');
  pm.expect(pm.response.json().run.current_phase).to.equal(9);
});

// GET /api/runs/{run_id}/events
pm.test("Phase 9 note has package_path", () => {
  const events = pm.response.json().events;
  const p9note = events.find(e => e.type === 'note' && e.phase === 9);
  pm.expect(p9note).to.exist;
  pm.expect(p9note.data.package_path).to.be.a('string');
  pm.expect(p9note.data.audit.audit_passed).to.be.true;
});
```

---

## UI Assertions

| Step | Action | Expected |
|------|--------|----------|
| 1 | Phase 9 card | "Completed", clickable ← fix verification |
| 2 | Packaging view | Package path displayed |
| 3 | Download ZIP button | Visible (currently no-op — BUG-006, known) |
| 4 | Executive summary section | Disease name, n_candidates, cost |
| 5 | Audit passed badge | Green "Audit ✓" chip |
| 6 | After run completes | RunCanvas shows phase overview (not auto-jump to P1) ← fix verification |

---

## What "PASS" Means for Phase 9

- [ ] `audit_passed: true`
- [ ] `package_path` non-null
- [ ] `candidates_total` ≥ 1
- [ ] `status: "completed"` in runs table
- [ ] All 10 phase cards (P0–P9) show "Completed" in RunCanvas overview
- [ ] Opening the completed run lands on **phase grid overview** (not P1 auto-jump) ← fix verification
