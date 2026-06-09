# Phase 1 — Target Identification (PU Learning)

**Runner:** `src/phases/phase1/runner.py`
**Duration:** ~15 minutes (30 bags, 20K genes)
**Skill:** `/postman` for API, `/test-master` for unit tests, `/verify` for UI

---

## What Phase 1 Does

1. Normalizes disease → EFO ID (via Open Targets API or provided)
2. Pulls tractability + genetic association scores from Open Targets
3. Expands positive set from OT-GA ≥ 0.5 threshold
4. Builds 14-feature gene matrix (STRING-Node2Vec, DepMap, GTEx, AlphaMissense, etc.)
5. Runs bagging-PU LightGBM (30 bags, LOO-AUROC)
6. Annotates master regulators via DoRothEA
7. Fetches genetic evidence (GWAS + OMIM + Jensen DISEASES)
8. Computes STRING degree centrality as `ppi_eigenvector`
9. Annotates Pharos TDL
10. Ranks, thresholds at score ≥ 0.50, writes targets to DB

---

## Input

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
  "pu_n_bags": 30,
  "through_phase": 1
}
```

---

## Expected Output JSON (phase_results.output_json)

```json
{
  "ranked_targets": [
    {
      "rank": 1,
      "symbol": "KRAS",
      "aggregate_score": 0.9xx,
      "tdl": "Tclin",
      "seeded": true,
      "evidence_trail": {
        "xgb_probability": 0.9xx,
        "pu_bio_score": 0.9xx,
        "pu_percentile": 99.x,
        "ot_genetic_assoc": 0.xx,
        "is_master_regulator": false,
        "shap_top": [{ "feature": "essentiality", "value": 0.32 }],
        "tractability": 0.xx,
        "genetic": 0.xx,
        "ppi_eigenvector": 0.xx
      }
    }
  ],
  "efo_id": "EFO_0002618",
  "disease_label": "pancreatic carcinoma",
  "model": {
    "method": "bagging-PU",
    "estimator": "lightgbm",
    "auroc_loo": 0.xxx,
    "n_positives": 15,
    "n_genes": 19500
  },
  "wall_time_s": 850.0
}
```

---

## Expected DB State After

**Table: `runs`**
| Column | Value |
|--------|-------|
| `status` | `"completed"` |
| `current_phase` | `1` |
| `efo_id` | `"EFO_0002618"` |

**Table: `phase_results`** (phase=1)
| Column | Value |
|--------|-------|
| `status` | `"completed"` |
| `output_json.model.auroc_loo` | > 0.65 |
| `output_json.n_targets` (len of ranked_targets) | 5–20 |

**Table: `targets`** (20 rows for this run)
| Column | Value |
|--------|-------|
| `rank` | 1–20 (no gaps, no duplicates) |
| `symbol` | HGNC symbol, non-null |
| `aggregate_score` | 0.50–1.0 for all except seeded |
| `tdl` | one of: Tclin, Tchem, Tbio, Tdark, unknown |
| `evidence_trail.xgb_probability` | matches aggregate_score |
| `evidence_trail.tractability` | float 0–1 |
| `evidence_trail.genetic` | float 0–1 |
| `evidence_trail.ppi_eigenvector` | float 0–1 |

---

## API Assertions (Postman)

```javascript
// GET /api/runs/{run_id}/targets

pm.test("Status 200", () => pm.response.to.have.status(200));

pm.test("At least 5 targets returned", () => {
  pm.expect(pm.response.json().targets.length).to.be.at.least(5);
});

pm.test("All known positives present", () => {
  const symbols = pm.response.json().targets.map(t => t.symbol);
  ['KRAS', 'TP53', 'SMAD4', 'CDKN2A', 'BRCA2'].forEach(kp => {
    pm.expect(symbols).to.include(kp);
  });
});

pm.test("xgb_probability key exists (bug fix verification)", () => {
  pm.response.json().targets.forEach(t => {
    pm.expect(t.evidence_trail).to.have.property('xgb_probability');
    pm.expect(t.evidence_trail.xgb_probability).to.be.a('number');
  });
});

pm.test("Phase-2 compat keys present", () => {
  const t = pm.response.json().targets[0];
  pm.expect(t.evidence_trail).to.have.property('tractability');
  pm.expect(t.evidence_trail).to.have.property('genetic');
  pm.expect(t.evidence_trail).to.have.property('ppi_eigenvector');
});

pm.test("Ranks are sequential starting at 1", () => {
  const ranks = pm.response.json().targets.map(t => t.rank).sort((a,b) => a-b);
  ranks.forEach((r, i) => pm.expect(r).to.equal(i + 1));
});

pm.test("AUROC above 0.65", () => {
  // check via /api/runs/{id} phase_results
  // this assertion goes on GET /api/runs/{run_id}
});
```

---

## UI Assertions

| Step | Action | Expected |
|------|--------|----------|
| 1 | Launch through_phase=1, wait ~15 min | Phase 1 card shows "Completed" |
| 2 | Target list (left panel) | Shows ranked targets with rank numbers and scores |
| 3 | Click "KRAS" in target list | Phase 1 detail updates to show KRAS evidence |
| 4 | SHAP bars in P1 detail | Renders top features (essentiality, STRING degree, etc.) |
| 5 | Seeded-star icon (★) | Visible on KRAS, TP53, SMAD4, CDKN2A, BRCA2 |
| 6 | ★ based on `xgb_probability > 0` | Should appear (was broken before fix — `xgb_probability` was undefined) |
| 7 | Phases 5–9 cards | Show "Pending", NOT "NOT YET IMPLEMENTED" ← fix verification |
| 8 | Topbar phase pill | "P1 Target ID" highlighted during run |

---

## Unit Test Cases (for `/test-master`)

```python
# src/phases/phase1/pu_model.py
def test_run_pu_learning_requires_positives_in_matrix():
    """Zero valid positives → RuntimeError, not silent failure."""

def test_run_pu_learning_auroc_above_random():
    """With known positives, AUROC > 0.60 on PDAC gene set."""

def test_evidence_trail_has_xgb_probability():
    """evidence_trail dict must contain 'xgb_probability' key."""

def test_seeded_targets_always_in_ranked_output():
    """known_positives appear in ranked list even below PU floor."""

def test_phase2_compat_keys_non_null():
    """tractability, genetic, ppi_eigenvector all present and float."""
```

---

## Failure Cases to Test

### F1-1: Zero positives in gene universe
- Pass `known_positives: ["FAKEGENE999"]`
- Expected: Phase 1 fails with RuntimeError
- Expected: `run-error-banner` visible in UI with helpful message

### F1-2: String embedding missing (first run)
- Delete `string_node2vec_512.parquet`
- Phase 1 should precompute it (takes ~10 extra minutes) then succeed

### F1-3: AUROC below floor
- Pass only 1 positive (backend requires ≥1, but model may not converge)
- Observe: model runs, AUROC may be near 0.5 (random)
- Expected: run still completes; AUROC logged to output_json

---

## What "PASS" Means for Phase 1

- [ ] AUROC(LOO) ≥ 0.65
- [ ] All 5 known positives in ranked target list
- [ ] `xgb_probability` present in every evidence_trail (fix verification)
- [ ] `tractability`, `genetic`, `ppi_eigenvector` all non-null floats
- [ ] Targets table has ≥ 5 rows for this run_id
- [ ] Phase 1 card shows "Completed" in UI
- [ ] ★ seeded icons visible on known positives in target list
- [ ] `wall_time_s` < 1800 (30 min hard cap)
