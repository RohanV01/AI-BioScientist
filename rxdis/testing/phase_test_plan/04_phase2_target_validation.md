# Phase 2 — Target Validation (Biophysical)

**Runner:** `src/phases/phase2/runner.py`
**Duration:** ~30 minutes (structure fetch + fpocket per target)
**Skill:** `/postman` for API, `/test-master` for unit tests, `/verify` for UI

---

## What Phase 2 Does

Per target (top 20 from Phase 1):
1. **Essentiality** — DepMap Chronos CRISPR scores
2. **Structure** — AFDB/RCSB waterfall (AF2 → RCSB → none)
3. **Pockets** — fpocket druggability scoring
4. **Variants** — AlphaMissense high-pathogenicity missense count
5. **Expression + Safety** — GTEx tissue TPM, tissue-specificity index
6. **Tractability** — rule engine → modality scores (SM/AB/PROTAC/peptide/oligo)
7. **LLM gate 2.8** — grey-zone modality resolution
8. **Validation score** — weighted linear + SHAP attributions
9. **LLM gate 2.9** — evidence narrative for medicinal chemist

---

## Input

Phase 1 output (auto-piped). For manual testing:
```json
{
  "through_phase": 2,
  "disease": "pancreatic cancer",
  "known_positives": ["KRAS", "TP53", "SMAD4", "CDKN2A", "BRCA2"],
  "indication_type": "oncology",
  "tissue_of_interest": "Pancreas",
  "provider": "lmstudio",
  "target_count_max": 20,
  "pu_n_bags": 30
}
```

---

## Expected Output JSON (phase_results.output_json)

```json
{
  "validated_targets": [ ... ],
  "n_total": 20,
  "n_passing": 8,
  "threshold_used": 0.50,
  "wall_time_s": 1800.0
}
```

---

## Expected DB State After

**Table: `targets`** (rows updated, not re-inserted)
| Column | Value |
|--------|-------|
| `validation_score` | 0.0–1.0 (non-null after Phase 2) |
| `modality_primary` | one of: SM, AB, PROTAC, peptide, oligo, unknown |
| `modality_secondary` | string or null |
| `evidence_trail.phase2` | non-null JSONB block |
| `evidence_trail.phase2.structure.source` | alphafold \| rcsb \| none |
| `evidence_trail.phase2.essentiality.chronos_median` | float or null |
| `evidence_trail.phase2.pockets` | array (may be empty) |
| `evidence_trail.phase2.passed` | true or false |

**Table: `decisions`**
| Column | Value |
|--------|-------|
| `phase` | 2 |
| `gate` | `"2.8_tractability_edge_{SYMBOL}"` or `"2.9_narrative_{SYMBOL}"` |
| Present only for grey-zone targets | — |

---

## API Assertions (Postman)

```javascript
// GET /api/runs/{run_id}/targets (after Phase 2 completes)

pm.test("validation_score populated", () => {
  pm.response.json().targets.forEach(t => {
    pm.expect(t.validation_score).to.not.be.null;
    pm.expect(t.validation_score).to.be.a('number');
  });
});

pm.test("phase2 block present in evidence_trail", () => {
  pm.response.json().targets.forEach(t => {
    pm.expect(t.evidence_trail).to.have.property('phase2');
    pm.expect(t.evidence_trail.phase2).to.have.property('structure');
    pm.expect(t.evidence_trail.phase2).to.have.property('essentiality');
    pm.expect(t.evidence_trail.phase2).to.have.property('modality');
  });
});

pm.test("modality_primary set on each target", () => {
  pm.response.json().targets.forEach(t => {
    pm.expect(['SM','AB','PROTAC','peptide','oligo','unknown']).to.include(t.modality_primary);
  });
});

pm.test("At least 3 targets passing validation", () => {
  const passing = pm.response.json().targets.filter(t => t.evidence_trail.phase2?.passed === true);
  pm.expect(passing.length).to.be.at.least(3);
});

// GET /api/runs/{run_id}/decisions
pm.test("LLM decisions logged for grey-zone targets", () => {
  const decisions = pm.response.json().decisions;
  const p2decisions = decisions.filter(d => d.phase === 2);
  // May be 0 if no grey-zone targets — PLAUSIBLE not REQUIRED
  pm.expect(p2decisions).to.be.an('array');
});
```

---

## UI Assertions (`/verify`)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Click Phase 2 card → "View →" | Opens Target Validation detail view |
| 2 | Target list left panel | Each target row has validation score chip |
| 3 | Click KRAS | Right panel shows structure source, pocket score, essentiality |
| 4 | Structure section | Shows "alphafold" or "rcsb" with pLDDT score |
| 5 | Pocket druggability | Bar/number between 0 and 1 |
| 6 | Essentiality section | Chronos median shown (or "N/A" if not in DepMap) |
| 7 | Modality chip | Shows SM / AB / PROTAC / peptide / oligo |
| 8 | Passed/Failed badge | Green "PASS" or red "FAIL" chip per target |
| 9 | Force pass / Force drop buttons | Visible (currently no-ops — BUG-004, known) |
| 10 | AI Decision Rail | After pressing `a`, LLM gate cards for Phase 2 visible |

---

## Unit Test Cases (for `/test-master`)

```python
def test_validation_score_range():
    """validation_score must be 0.0–1.0 inclusive."""

def test_stub_entry_does_not_crash_phase3():
    """_stub_entry() returns shape compatible with Phase 3 runner."""

def test_fpocket_fallback_uses_ot_tractability():
    """When fpocket_ran=False and ot_tractability > 0, druggability = ot_tractability * 0.70."""

def test_threshold_lowered_when_few_pass():
    """When < 3 targets score ≥ 0.50, threshold drops to 0.30."""

def test_phase2_block_shape_matches_frontend_types():
    """_phase2_block() output keys match Phase2Data TypeScript interface."""
```

---

## Failure Cases to Test

### F2-1: All structures "none" (AFDB/RCSB unreachable)
- Disconnect internet or mock the structure endpoint to fail
- Expected: phase 2 continues with `max_druggability = 0` or OT proxy
- Expected: targets still score (not crash)

### F2-2: DepMap file missing
- Rename `CRISPRGeneEffect.csv`
- Expected: `essentiality: {}` per target, not a crash
- Expected: essentiality feature = 0.0 in validation score

### F2-3: All targets below threshold
- Use a fake disease with no real genetics (forces low scores)
- Expected: threshold auto-drops to 0.30, at least 3 targets pass
- Expected: `threshold_used: 0.30` in output_json

---

## What "PASS" Means for Phase 2

- [ ] `validation_score` non-null on all targets
- [ ] `evidence_trail.phase2` block present on all targets
- [ ] `modality_primary` set (not "unknown") on ≥ 50% of targets
- [ ] ≥ 3 targets with `passed: true`
- [ ] Phase 2 card shows "Completed" in UI
- [ ] Structure source rendered in UI (alphafold/rcsb/none)
- [ ] `wall_time_s` < 5400 (90 min hard cap)
