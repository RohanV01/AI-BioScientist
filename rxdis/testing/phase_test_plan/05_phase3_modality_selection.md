# Phase 3 — Modality Selection

**Runner:** `src/phases/phase3/runner.py` + `rule_engine.py`
**Duration:** ~2 minutes
**Skill:** `/postman` for API, `/verify` for UI

---

## What Phase 3 Does

1. Reads validated targets from Phase 2
2. Rule engine assigns primary/secondary modality and branch flags per target
3. Assigns `repurposing_priority` (HIGH / MEDIUM / LOW_CLINICAL / LOW)
4. LLM gate resolves grey-zone cases
5. Writes phase3 block into `evidence_trail` in targets table

---

## Input

```json
{ "through_phase": 3, ... (same as Phase 2 input) }
```

---

## Expected DB State After

**Table: `targets`** (phase3 block merged into evidence_trail)
```json
{
  "evidence_trail": {
    "phase3": {
      "symbol": "KRAS",
      "primary": "SM",
      "secondary": "PROTAC",
      "branches": ["SM", "repurposing"],
      "modality_scores": { "SM": 0.85, "AB": 0.2, "PROTAC": 0.6 },
      "repurposing_priority": "HIGH",
      "seed_smiles_opt": false,
      "greyzone_resolved": false,
      "concerns": []
    }
  }
}
```

---

## API Assertions (Postman)

```javascript
// GET /api/runs/{run_id}/targets (after Phase 3)

pm.test("phase3 block on all validated targets", () => {
  pm.response.json().targets.forEach(t => {
    if (t.evidence_trail.phase2?.passed) {
      pm.expect(t.evidence_trail).to.have.property('phase3');
    }
  });
});

pm.test("modality_primary not 'unknown' after Phase 3", () => {
  pm.response.json().targets
    .filter(t => t.evidence_trail.phase2?.passed)
    .forEach(t => {
      pm.expect(t.modality_primary).to.not.equal('unknown');
    });
});

pm.test("repurposing_priority is valid value", () => {
  const valid = ['HIGH', 'MEDIUM', 'LOW_CLINICAL', 'LOW'];
  pm.response.json().targets.forEach(t => {
    if (t.evidence_trail.phase3) {
      pm.expect(valid).to.include(t.evidence_trail.phase3.repurposing_priority);
    }
  });
});
```

---

## UI Assertions

| Step | Action | Expected |
|------|--------|----------|
| 1 | Click Phase 3 "View →" | Opens Modality Routing view |
| 2 | Modality badge per target | SM / AB / PROTAC / peptide / oligo chips visible |
| 3 | Repurposing priority chip | HIGH / MEDIUM / LOW_CLINICAL / LOW |
| 4 | Branch flags | SM branch / Biologic branch indicators |
| 5 | Grey-zone targets | "LLM Resolved" tag if greyzone_resolved=true |

---

## What "PASS" Means for Phase 3

- [ ] All passing P2 targets have `evidence_trail.phase3` block
- [ ] `modality_primary` not "unknown" on all passing targets
- [ ] `repurposing_priority` is one of the 4 valid values
- [ ] Phase 3 card shows "Completed" in UI (~2 min)
