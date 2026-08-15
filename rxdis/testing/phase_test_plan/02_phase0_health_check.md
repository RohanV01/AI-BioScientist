# Phase 0 — Setup & Health Check

**Runner:** `src/phases/phase0/runner.py`
**Duration:** ~5 seconds
**Skill:** `/postman` for API assertions, `/verify` for UI

---

## What Phase 0 Does

1. Checks all required env vars are present
2. Verifies local database files exist and are readable
3. Pings LLM provider (LM Studio / Anthropic / OpenAI)
4. Checks Supabase connectivity
5. Returns `go_no_go: "go"` or `"no_go"` with a list of missing items
6. Computes a rough cost estimate for the full run

---

## Input

```json
{
  "disease": "pancreatic cancer",
  "known_positives": ["KRAS", "TP53", "SMAD4", "CDKN2A", "BRCA2"],
  "intent_mode": "explore",
  "tissue_of_interest": "Pancreas",
  "indication_type": "oncology",
  "provider": "lmstudio",
  "target_count_max": 5,
  "pu_n_bags": 10,
  "through_phase": 0
}
```

---

## Expected DB State After

**Table: `runs`**
| Column | Expected value |
|--------|---------------|
| `status` | `"completed"` |
| `current_phase` | `0` |
| `disease_name` | `"pancreatic cancer"` |
| `intent_mode` | `"explore"` |

**Table: `phase_results`**
| Column | Expected value |
|--------|---------------|
| `phase` | `0` |
| `status` | `"completed"` |
| `output_json.go_no_go` | `"go"` |
| `output_json.missing_required` | `[]` |
| `started_at` | non-null |
| `finished_at` | non-null |

---

## API Assertions (Postman)

```javascript
// After POST /api/runs completes (poll until status = completed)

// GET /api/runs/{run_id}
pm.test("Phase 0 completed", () => {
  const p0 = pm.response.json().phases.find(p => p.phase === 0);
  pm.expect(p0.status).to.equal('completed');
});
pm.test("Run status completed", () => {
  pm.expect(pm.response.json().run.status).to.equal('completed');
});

// GET /api/runs/{run_id}/events
pm.test("go_no_go = go in event stream", () => {
  const events = pm.response.json().events;
  const p0note = events.find(e => e.type === 'note' && e.phase === 0);
  pm.expect(p0note).to.exist;
  pm.expect(p0note.data.go_no_go).to.equal('go');
});
pm.test("No missing_required items", () => {
  const events = pm.response.json().events;
  const p0note = events.find(e => e.type === 'note' && e.phase === 0);
  pm.expect(p0note.data.missing_required).to.have.lengthOf(0);
});
```

---

## UI Assertions

| Step | Action | Expected |
|------|--------|----------|
| 1 | Launch run with `through_phase: 0` | RunCanvas opens |
| 2 | Phase 0 card | Status chip turns green "Completed" within 10s |
| 3 | Phase 1–9 cards | All show "Pending" (not NOT IMPLEMENTED for 5–9) |
| 4 | Click "View →" on Phase 0 card | Phase 0 detail or note renders |
| 5 | No error banner | Error banner (`run-error-banner`) should NOT be visible |

---

## Failure Cases to Test

### F0-1: Supabase unreachable
- Temporarily set wrong `SUPABASE_URL` in `.env`
- Restart backend
- POST /api/runs → run should fail immediately
- Expected: run event stream shows `{"type":"run","status":"failed","error":"Supabase unavailable..."}`
- Expected: `run-error-banner` visible in UI

### F0-2: Missing database file
- Temporarily rename `Databases/depmap/CRISPRGeneEffect.csv`
- POST run → Phase 0 should detect and return `go_no_go: "no_go"`
- Expected: `missing_required` contains the file name
- Expected: Phase 1 never starts

### F0-3: LLM provider unreachable (lmstudio not running)
- Stop LM Studio process
- POST run → Phase 0 should warn but still `go_no_go: "go"` (LLM is optional at P0)
- Phase 1 LLM calls should degrade gracefully (causal filter skips)

---

## What "PASS" Means for Phase 0

- [ ] `go_no_go: "go"` in output_json
- [ ] `missing_required: []`
- [ ] `status: "completed"` in runs table
- [ ] Phase 0 card green in UI within 10s of launch
- [ ] No error banner visible
