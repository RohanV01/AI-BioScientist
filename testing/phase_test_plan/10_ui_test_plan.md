# UI Test Plan (No Playwright)

**Tool:** Browser DevTools + manual walkthrough
**Skill for UI coverage:** `/verify` (behavioral verification)
**Skill for API-backed UI flows:** `/postman` (confirm network requests)

---

## Approach

No Playwright. Manual walkthrough using this checklist + DevTools open:
- Console tab: watch for JS errors
- Network tab: inspect request bodies and response payloads
- React DevTools (optional): inspect Zustand store state

---

## Test Environment Setup

```bash
# Terminal 1 — backend
source .venv/bin/activate && uvicorn src.api.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev

# Browser
open http://localhost:5173
# DevTools → Console + Network tab open throughout
```

---

## 1. Authentication Flow

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 1.1 | Open http://localhost:5173 | Login page shown (not app) | |
| 1.2 | Login with Supabase creds | Redirect to Home dashboard | |
| 1.3 | Hard refresh (F5) | Stays logged in (no redirect loop) | |
| 1.4 | Open DevTools Network | No 401 or 403 errors | |

---

## 2. Home Dashboard

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 2.1 | Dashboard loads | Summary stats visible (runs, targets, candidates) | |
| 2.2 | "Launch new run" button | Opens E2EConfig form | |
| 2.3 | Recent runs list | Shows past runs (or empty state) | |
| 2.4 | Sidebar | All nav items visible | |

---

## 3. E2EConfig Form (Launch)

Critical: this form was the source of the 422 bugs.

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 3.1 | Disease input | Free text field, accepts "pancreatic cancer" | |
| 3.2 | Indication dropdown | Shows exactly: oncology / chronic / acute | |
| 3.3 | Provider dropdown | Shows exactly: lmstudio / anthropic / openai | |
| 3.4 | Launch button click | Network: POST /api/runs shows 200 (not 422) | |
| 3.5 | Network request body | `provider: "lmstudio"`, `indication_type: "oncology"`, `pu_n_bags: 30` | |
| 3.6 | After launch | Navigates to RunCanvas for new run | |
| 3.7 | Try "chronic" indication | POST → 200 (not 422) | |
| 3.8 | Try "acute" indication | POST → 200 (not 422) | |

---

## 4. RunCanvas — Phase Grid

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 4.1 | While run in progress | Phase cards animate / show "In Progress" | |
| 4.2 | Completed run | All 10 phase cards (P0–P9) visible | |
| 4.3 | Phase 0–3 completed | Cards show "Completed" | |
| 4.4 | Phase 5–9 completed | Cards show "Completed" (not "NOT YET IMPLEMENTED") ← fix | |
| 4.5 | Click Phase 1 "View →" | Opens target list | |
| 4.6 | Click Phase 2 "View →" | Opens validation view | |
| 4.7 | Click Phase 3 "View →" | Opens modality routing view | |
| 4.8 | Open completed run from sidebar | Lands on phase grid (NOT auto-jumping to P1 detail) ← fix | |

---

## 5. Phase 1 — Target List

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 5.1 | Target list shown | ≥ 10 rows | |
| 5.2 | PU score column | Decimal numbers visible (not blank) ← fix | |
| 5.3 | Known-positive targets (KRAS, TP53) | "★" icon visible ← fix | |
| 5.4 | Click target row | Opens evidence trail drawer | |
| 5.5 | Evidence trail drawer | xgb_probability, pu_bio_score, genetic score visible | |
| 5.6 | Sort by score | Works, top targets shown first | |

---

## 6. Phase 2 — Validation

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 6.1 | Validation summary | n_passed / n_total counts shown | |
| 6.2 | SHAP drawer | Opens for each target | |
| 6.3 | SHAP tabs | Tractability / Essentiality / Localization tabs present | |
| 6.4 | Pass/Fail chip per target | Green PASS / Red FAIL | |

---

## 7. Phase 3 — Modality

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 7.1 | Modality chips per target | SM / AB / PROTAC / peptide chips | |
| 7.2 | Repurposing priority | HIGH / MEDIUM chips visible | |
| 7.3 | Branch flow diagram | If present, shows SM vs Biologic branch | |

---

## 8. Scorecard View

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 8.1 | Open Scorecard from nav | Phase 2+3 columns visible | |
| 8.2 | Per-target scores | Tractability, Essentiality, Localization columns | |
| 8.3 | Modality column | SM / PROTAC / AB per target | |
| 8.4 | Export button (if present) | CSV download triggers | |

---

## 9. AI Decision Rail

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 9.1 | Open AI Rail via button | Right-side drawer opens | |
| 9.2 | Decision cards visible | Phase-tagged AI reasoning cards | |
| 9.3 | Close AI Rail | Drawer closes | |
| 9.4 | Sidebar stays consistent | Sidebar width unaffected by rail toggle ← BUG-001 known | |

---

## 10. Sidebar

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 10.1 | Recent runs list | Past runs clickable | |
| 10.2 | Click module run | Navigates to that run ← fix | |
| 10.3 | No console error on click | No "Cannot read property of undefined" | |
| 10.4 | New run appears after launch | Sidebar updates without full refresh | |

---

## 11. Telemetry / Compute Strip

| # | Action | Expected | Pass? |
|---|--------|----------|-------|
| 11.1 | Compute strip visible | Shows CPU / GPU / wall time | |
| 11.2 | Updates during run | Compute values change as phases run | |
| 11.3 | WebSocket connected | No "WS disconnected" banner | |

---

## 12. Known UI Bugs (Do Not Mark as Failures)

| Bug | Description | Status |
|-----|-------------|--------|
| BUG-001 | Sidebar and AI Rail share `railOpen` state | Open — needs store split |
| BUG-002 | Gene search uses 10-gene mock | Open — needs `/api/genes?q=` wiring |
| BUG-003 | SYS_CHECKS hardcoded | Open — needs real `/api/health` data |
| BUG-004 | EFO lookup fake | Open — only resolves "pancreatic" |
| BUG-005 | "Stop early"/"Run more" buttons no-op | Open |
| BUG-006 | Download ZIP button no-op | Open |

---

## Network Tab: What to Watch For

```
422 Unprocessable Entity  → payload validation failure (provider/indication_type enum mismatch)
401 Unauthorized          → Supabase JWT expired
403 Forbidden             → RLS policy blocked query
404 Not Found             → wrong run_id or endpoint doesn't exist yet
ERR_CONNECTION_REFUSED    → backend not running on :8000
```
