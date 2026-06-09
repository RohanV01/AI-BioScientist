# Bug Tracker

Living document. Add rows as new bugs are found. Mark FIXED when patch lands.

---

## Open Bugs

| ID | Severity | Component | Description | Root Cause | Fix Path |
|----|----------|-----------|-------------|------------|----------|
| BUG-001 | MEDIUM | `store.ts`, `Sidebar.tsx` | Sidebar expand and AI Decision Rail share `railOpen` state — toggling rail changes sidebar width | `const expanded = railOpen` in Sidebar reuses same flag | Split into `sidebarExpanded` + `railOpen` in Zustand store |
| BUG-002 | LOW | `E2EConfig.tsx` L8-19 | Gene search uses hardcoded 10-gene mock, not real gene DB | Frontend never wired to `/api/genes?q=` endpoint | Wire `useEffect` to debounced `GET /api/genes?q=` |
| BUG-003 | LOW | `E2EConfig.tsx` L28 | `SYS_CHECKS` hardcoded static object | No call to `/api/health` to fetch real status | Call `GET /api/health` on mount, map to `SYS_CHECKS` |
| BUG-004 | LOW | `E2EConfig.tsx` | EFO lookup fake — only resolves "pancreatic" substring | Hardcoded stub | Wire to real EFO ontology lookup or Open Targets `/efo` |
| BUG-005 | LOW | Phase 7 (MPO) UI | "Stop early" and "Run more" buttons are no-op alerts | Not implemented | Requires backend signal endpoints + store action |
| BUG-006 | LOW | Phase 9 (Packaging) UI | "Download ZIP" button no-op | No file-serve endpoint on backend | Add `GET /api/runs/{id}/package` → serve ZIP |
| BUG-007 | LOW | `targets` schema | `seeded` boolean field accepted by `run_state.upsert_target()` but column doesn't exist | Schema gap — column was never added | `ALTER TABLE targets ADD COLUMN seeded boolean DEFAULT false` |
| NEW-B01 | LOW | `src/api/main.py` | `POST /api/runs` with `disease:""` or `known_positives:[]` returns HTTP 400 instead of 422 | Validation done in route handler, not Pydantic model | Move to `@field_validator` in `RunRequest` |
| NEW-B02 | HIGH | `src/phases/phase1/runner.py` | Duplicate target rows (42 rows, 22 unique symbols) in completed runs | `clear_targets` may not run before upsert, or Phase 1 ran twice | Add `DELETE FROM targets WHERE run_id=?` before upsert loop, or add UNIQUE constraint on `(run_id, symbol)` |
| NEW-B03 | HIGH | `src/phases/phase2/runner.py` | Phase 2 marks "completed" + logs 459s wall time but `validation_score` and `evidence_trail.phase2` are NULL on all targets — silent data loss | DB upsert call silently failing with no error propagation | Add try/except + logging around every `upsert_target()` call in Phase 2; check RLS policy allows UPDATE |
| NEW-B04 | MEDIUM | `src/api/events.py` | `GET /api/runs/{id}/events` returns `events:[]` after server restart — EventHub is in-memory only | No DB-backed event persistence; hub evicts on restart | Persist events to a new `events` table; replay from DB in `/events` endpoint |
| NEW-B05 | MEDIUM | `src/api/orchestrator.py` | LLM provider offline → `go_no_go:no_go` blocks entire run from starting | Phase 0 treats LLM connectivity as hard blocker | Make LLM check a warning-only (soft) gate, or document clearly that LM Studio must be running |
| NEW-B06 | HIGH | `src/api/main.py` `_get_targets()` | `xgb_probability` is written to DB by `runner.py` (lines 261, 313) but missing from API response — `isSeeded` check in `RunCanvas.tsx:369` always false, ★ star never renders | `_get_targets()` SELECT or serialisation does not include `xgb_probability` from `evidence_trail` | Add `xgb_probability` to the `evidence_trail` keys returned in `_get_targets()` |

---

## Fixed Bugs

| ID | Severity | Component | Description | Fix Applied | File(s) Changed |
|----|----------|-----------|-------------|-------------|-----------------|
| BUG-F01 | CRITICAL | `E2EConfig.tsx` L113 | `provider: 'local'` → 422 on every run launch | Changed to `'lmstudio'` | `E2EConfig.tsx` |
| BUG-F02 | CRITICAL | `E2EConfig.tsx` L40 | INDICATIONS had invalid values (neurology, cardiovascular, rare disease) | Changed to `['oncology', 'chronic', 'acute']` | `E2EConfig.tsx` |
| BUG-F03 | HIGH | `store.ts` L60 | `IMPLEMENTED_MAX = 4` → phases 5–9 falsely "NOT YET IMPLEMENTED" | Changed to `9` | `store.ts` |
| BUG-F04 | HIGH | `RunCanvas.tsx` L18 | `isImplemented = phaseNum <= 3` → phases 4–9 greyed out | Changed to `phaseNum <= 9` | `RunCanvas.tsx` |
| BUG-F05 | MEDIUM | `store.ts` L279 | Completed runs auto-jump to Phase 1 detail | Partial — `phaseView:1` removed from openRun handler BUT SSE `_applyBatch` line 385 still sets `if (!phaseView) phaseView = 1` on run:completed event replay → still auto-jumps | `store.ts` |
| BUG-F06 | HIGH | `phase1/runner.py` L261, L313 | `xgb_probability` undefined in UI | Partial — runner now writes both keys BUT `_get_targets()` in `main.py` does not return `xgb_probability` in API response → ★ star still broken (see NEW-B06) | `src/phases/phase1/runner.py` |
| BUG-F07 | MEDIUM | `Sidebar.tsx` L167-179 | Module run rows in sidebar unclickable | Added `onClick={() => handleOpenRun(mr.id)}` | `frontend/src/components/Sidebar.tsx` |
| BUG-F08 | MEDIUM | `E2EConfig.tsx` L115 | `pu_n_bags` hardcoded 10/5, undersampling PU model | Changed to `30` (matches backend default) | `E2EConfig.tsx` |

---

## Refuted Bugs (Investigated, Not Issues)

| ID | Description | Investigation Result |
|----|-------------|---------------------|
| CAND-01 | `validation_score` missing from schema | `schema.sql` L58 has `validation_score numeric` — column exists |
| CAND-02 | `activeDisease` race condition on run open | `openRun(fresh=true)` path has no actual race — fetches are gated correctly |

---

## How to Add a New Bug

```markdown
| BUG-NNN | SEVERITY | Component | One-line description | Root cause if known | What it takes to fix |
```

Severity scale:
- **CRITICAL**: Blocks all runs (e.g., 422 on launch)
- **HIGH**: Data loss or wrong results visible to user
- **MEDIUM**: Feature broken but workaround exists
- **LOW**: Polish / cosmetic / nice-to-have
