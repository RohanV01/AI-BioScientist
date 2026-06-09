# Phase 4 — Drug Repurposing

**Runner:** `src/phases/phase4/runner.py`
**Duration:** ~2 hours (ChEMBL + LINCS + Vina docking per target)
**Skill:** `/postman` for API, `/verify` for UI
**Intent mode required:** `explore` or `repurpose`

---

## What Phase 4 Does

Per validated target:
1. **ChEMBL query** — fetch approved/clinical drugs with activity data
2. **LINCS transcriptomics** — score drug-disease signature alignment (Tau score)
3. **PrimeKG query** — drug-gene relationship evidence
4. **Vina docking** — AutoDock Vina 1.2.7 screen of top ChEMBL candidates
5. **Scoring** — combined repurposing score (clinical stage + Tau + Vina + KG)
6. Writes candidates to `candidates` table

---

## Input

```json
{
  "through_phase": 4,
  "intent_mode": "repurpose",
  "disease": "pancreatic cancer",
  "known_positives": ["KRAS", "TP53", "SMAD4", "CDKN2A", "BRCA2"],
  "indication_type": "oncology",
  "tissue_of_interest": "Pancreas",
  "provider": "lmstudio",
  "target_count_max": 5,
  "pu_n_bags": 10
}
```

Use `target_count_max: 5` and `pu_n_bags: 10` to limit wall time during testing.

---

## Expected Output JSON

```json
{
  "n_targets_screened": 5,
  "n_candidates_total": 18,
  "wall_time_s": 7200.0
}
```

---

## Expected DB State After

**Table: `candidates`**
| Column | Value |
|--------|-------|
| `kind` | `"repurposing"` |
| `target_id` | gene symbol (e.g. `"KRAS"`) |
| `identifier` | ChEMBL ID (e.g. `"CHEMBL2107884"`) |
| `smiles` | valid SMILES string |
| `combined_score` | 0.0–1.0 |
| `subscores.phase` | 4 |
| `subscores.rank` | integer |
| `subscores.passed` | true or false |

---

## API Assertions (Postman)

```javascript
// No dedicated /api/runs/{id}/candidates endpoint yet.
// Verify via Supabase directly OR check compute log.

// GET /api/runs/{run_id}/compute
pm.test("Phase 4 compute entry present", () => {
  const compute = pm.response.json().compute;
  const p4 = compute.find(c => c.phase === 4);
  pm.expect(p4).to.exist;
  pm.expect(p4.wall_time_s).to.be.a('number');
});

// GET /api/runs/{run_id}
pm.test("current_phase = 4 after completion", () => {
  pm.expect(pm.response.json().run.current_phase).to.equal(4);
});
```

---

## UI Assertions

| Step | Action | Expected |
|------|--------|----------|
| 1 | Click Phase 4 "View →" | Opens Drug Repurposing view |
| 2 | Candidate table | Rows with drug name, Vina score, LINCS Tau, clinical stage |
| 3 | Filter by target | Shows candidates for selected gene |
| 4 | Phase 4 card | "Completed" with wall time note |

---

## What "PASS" Means for Phase 4

- [ ] `n_candidates_total` ≥ 1
- [ ] `candidates` table has rows with `kind: "repurposing"`
- [ ] `combined_score` between 0 and 1
- [ ] `smiles` non-null on each candidate
- [ ] Phase 4 card "Completed" in UI
