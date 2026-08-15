# RxDis Phase Test Plan

End-to-end quality gate for the 9-phase drug discovery pipeline.
Each phase has its own file: inputs, expected outputs, DB state, API contracts, UI checks, and known failures.

---

## Folder Structure

```
testing/phase_test_plan/
  README.md                      ← you are here
  00_prerequisites.md            ← env setup, test fixtures, skill setup
  01_api_contracts.md            ← Postman collection structure, all endpoints
  02_phase0_health_check.md      ← Phase 0: Setup & Health
  03_phase1_target_id.md         ← Phase 1: Target Identification (PU Learning)
  04_phase2_target_validation.md ← Phase 2: Target Validation (biophysical)
  05_phase3_modality_selection.md← Phase 3: Modality Selection (rule engine + LLM)
  06_phase4_drug_repurposing.md  ← Phase 4: Drug Repurposing (ChEMBL + Vina)
  07_phase5_6_denovo.md          ← Phase 5+6: De Novo SM + Biologic Design
  08_phase7_8_mpo_validation.md  ← Phase 7+8: MPO Optimization + Validation Gate
  09_phase9_packaging.md         ← Phase 9: Packaging & Report
  10_ui_test_plan.md             ← Manual UI checklist + /verify skill guide
  11_bug_tracker.md              ← All known bugs, status, owner
  12_regression_checklist.md     ← 5-min quick smoke test before any commit
```

---

## Skill Matrix — Which Skill for Which Layer

| Layer | Skill | When to use |
|-------|-------|-------------|
| API contracts | `/postman` | Test every REST endpoint, request/response shape, auth, error codes |
| API agent-readiness | `/postman-api-readiness` | Check the OpenAPI spec scores 8 AI-agent pillars |
| Backend unit tests | `/test-master` | Generate pytest fixtures and assertions per phase runner |
| UI visual testing | `/verify` | Run the live app and confirm specific UI behavior |
| UI E2E automation | `/playwright-expert` | Write and maintain Playwright test suite |
| Deep bug triage | `/debugging-wizard` | When a specific phase fails and logs are unclear |
| Security audit | `/security-review` | Before any public deployment |

---

## Standard Test Disease (used in every phase file)

```json
{
  "disease": "pancreatic cancer",
  "disease_efo_id": "EFO_0002618",
  "known_positives": ["KRAS", "TP53", "SMAD4", "CDKN2A", "BRCA2"],
  "intent_mode": "explore",
  "tissue_of_interest": "Pancreas",
  "indication_type": "oncology",
  "provider": "lmstudio",
  "target_count_max": 20,
  "pu_n_bags": 30
}
```

This set is scientifically validated: all 5 positives are confirmed PDAC targets and exist in the gene universe.

---

## Test Execution Order

```
Prerequisites → API Contracts (Postman) → Phase 0 → Phase 1 → Phase 2 → Phase 3
→ Phase 4 (repurpose intent) → Phase 5+6 (de_novo intent) → Phase 7+8 → Phase 9
→ UI Manual Checklist → Regression Checklist
```

Each phase file is self-contained: you can jump to any phase if you already have a valid run_id.

---

## Pass / Fail Definition

- **PASS**: All assertions in the file's "Expected Output" section hold.
- **PARTIAL**: ≥ 75% assertions pass; known bugs account for the rest (documented in 11_bug_tracker.md).
- **FAIL**: Any assertion in the CRITICAL section fails.

---

## How to Run a Test Phase

1. Start the backend: `source .venv/bin/activate && uvicorn src.api.main:app --reload --port 8000`
2. Start the frontend: `cd frontend && npm run dev`
3. Open the relevant phase file, follow the steps top-to-bottom.
4. Use `/postman` to run API assertions — the collection is defined in `01_api_contracts.md`.
5. Use `/verify` for UI assertions — pass the checklist section from `10_ui_test_plan.md`.
6. Log any failure in `11_bug_tracker.md`.
