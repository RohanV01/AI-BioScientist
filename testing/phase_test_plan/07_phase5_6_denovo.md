# Phase 5+6 — De Novo Small Molecule + Biologic Design

**Runners:** `src/phases/phase5/runner.py`, `src/phases/phase6/runner.py`
**Duration:** Phase 5 ~8h, Phase 6 ~4h
**Intent mode required:** `explore` or `de_novo`

---

## Phase 5 — De Novo Small Molecule

### What it does
1. Fragment-based generation via BRICS (RDKit) as fast fallback
2. REINVENT4 generative model (if configured)
3. ADMET filtering (ADMETlab or local rules)
4. Lipinski / QED / SA score filters
5. Initial Vina docking screen

### Expected Output
```json
{
  "n_targets": 5,
  "n_candidates_total": 50,
  "wall_time_s": 28800.0
}
```

### DB State
**`candidates` table** — `kind: "sm"`, `smiles` non-null, `combined_score` 0–1

### Minimal Test (reduce runtime)
```json
{
  "through_phase": 5,
  "intent_mode": "de_novo",
  "target_count_max": 1,
  "pu_n_bags": 5
}
```

### API Assertions (Postman)
```javascript
// GET /api/runs/{run_id}/compute
pm.test("Phase 5 entry present", () => {
  const p5 = pm.response.json().compute.find(c => c.phase === 5);
  pm.expect(p5).to.exist;
});
```

### UI Assertions
| Step | Action | Expected |
|------|--------|----------|
| 1 | Phase 5 card | Shows "Completed" (not "NOT YET IMPLEMENTED") ← fix verification |
| 2 | Click "View →" | Small Molecule Design view with candidate table |
| 3 | SMILES structures | Rendered or SMILES string visible |
| 4 | ADMET flags | Pass/fail badges |

### What "PASS" Means
- [ ] Phase 5 card clickable (not greyed out) — fix verification
- [ ] ≥ 1 SM candidate in `candidates` table
- [ ] `smiles` non-null, valid SMILES
- [ ] `combined_score` ∈ [0, 1]

---

## Phase 6 — De Novo Biologic Design

### What it does
1. LLM peptide generation (Claude/GPT/LM Studio)
2. ProteinMPNN sequence design
3. Boltz-2 / RFdiffusion structure prediction (if NIM API configured)
4. Developability filters (charge, hydrophobicity, instability index)
5. iPTM / PAE scoring

### Expected Output
```json
{
  "n_targets": 5,
  "n_candidates_total": 15,
  "wall_time_s": 14400.0
}
```

### DB State
**`candidates` table** — `kind: "biologic"`, `sequence` non-null

### API Assertions (Postman)
```javascript
// GET /api/runs/{run_id}/compute
pm.test("Phase 6 entry present", () => {
  const p6 = pm.response.json().compute.find(c => c.phase === 6);
  pm.expect(p6).to.exist;
});
```

### UI Assertions
| Step | Action | Expected |
|------|--------|----------|
| 1 | Phase 6 card | "Completed" (not greyed out) ← fix verification |
| 2 | Biologic Design view | Candidate table with sequence, modality, iPTM |
| 3 | Modality column | peptide / nanobody / mAb |
| 4 | Structure viewer | 3D viewer or sequence display |

### What "PASS" Means
- [ ] Phase 6 card clickable
- [ ] ≥ 1 biologic candidate with non-null `sequence`
- [ ] `subscores.iptm` present (may be null if Boltz-2 not run)
