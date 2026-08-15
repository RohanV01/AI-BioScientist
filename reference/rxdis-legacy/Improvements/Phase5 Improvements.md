# Phase 5 — De Novo Small Molecule Design: Rationale, Gaps & Improvement Scope

## Scientific Rationale

Phase 5 answers: **"Can we computationally design novel small molecules that bind the validated target with favorable pharmacokinetic and pharmacodynamic properties?"**

It runs a generative chemistry pipeline conditioned on known binders:

1. **5.1 Seed collection** — ChEMBL binders (pChEMBL ≥7) + user-supplied SMILES as templates
2. **5.2 Generation** — REINVENT4 Mol2Mol (primary): generative ML produces ~1,000 analogs. BRICS fragmentation (fallback): RDKit decomposes known binders and recombines fragments
3. **5.3 Medicinal chemistry filters** — Ro5, Veber, PAINS, synthetic accessibility (SA score <6), QED ≥0.3, Tanimoto novelty filter (<0.7 to approved drugs)
4. **5.4 ADMET scoring** — RDKit descriptor-based local prediction: hERG, AMES mutagenicity, BBB penetration, hepatotoxicity, Caco-2 absorption, aqueous solubility (logS)
5. **5.5 Docking** — Vina re-dock against Phase 2 pocket (exhaustiveness=4)
6. **5.6 LLM gate** — Claude generates optimization narrative for top-5: verdict (pass/borderline/fail), key concern, structural modifications suggested

**Combined scoring formula:**
```
combined_pre8 = 0.40 × vina_norm + 0.25 × admet_score + 0.20 × qed + 0.15 × novelty
```
Pass gate: `combined_pre8 ≥ 0.35 AND admet_score ≥ 0.5 AND vina ≤ −7.0 kcal/mol`

---

## What Information Is Incomplete / Missing from the UI

### A. Hardcoded / fake values — none in the main view

Phase 5 does not have prominent hardcoded stats like Phases 3/4. The main gap is that the backend data never reaches the UI at all (see section B).

### B. Critical blockers — data never persists or loads

**1. `run_state.insert_candidate()` does not exist**
Phase 5 `runner.py` calls this function (line 437) to write results to the `candidates` table. The function is not defined anywhere in `src/db/run_state.py`. All computed candidates are silently discarded after the run.

**2. `GET /api/runs/{run_id}/candidates` endpoint does not exist**
The frontend `useCandidates()` hook calls this endpoint. It is not implemented in `src/api/main.py`. Even if candidates were persisted, the frontend cannot fetch them.

These two missing pieces mean **Phase 5 computes everything correctly but produces zero visible output.**

### C. Data computed but never displayed (once plumbing is fixed)

| Backend field | What it is | Why it matters |
|---|---|---|
| `admet_score` (0–1) | Composite ADMET penalty score | Primary safety filter — the single most important number after vina |
| `admet.hERG` | Cardiac risk: low/medium/high | hERG high-risk is a hard disqualifier |
| `admet.AMES` | Mutagenicity: neg/pos | AMES positive = genotoxic concern; critical for candidate selection |
| `admet.BBB` | Blood-brain barrier penetration | Required for CNS indications; liability for non-CNS |
| `admet.hepatox` | Hepatotoxicity alert | Liver toxicity flag |
| `admet.logS` | Aqueous solubility | Low solubility (logS < −6) is a formulation blocker |
| `admet.disqualifying` | List of hard failures | e.g. `["AMES_mutagenic", "hERG_high_risk"]` — the reason a candidate was rejected |
| `admet.concerns` | Non-fatal warnings | e.g. `["hERG_medium_risk", "low_solubility"]` |
| `narrative` | LLM verdict + modifications | Expert chemical rationale + suggested structural improvements |
| `novelty` | 1 − max_tanimoto_to_approved | How chemically distinct is this from known drugs |
| `pains_flags` | PAINS alert list | Reactive/promiscuous groups that cause false positives in assays |
| `tpsa`, `rotb` | Veber filter descriptors | Oral bioavailability predictors |
| `passed` | Boolean gate result | Whether candidate cleared all thresholds |
| `combined_pre8` | Final composite score | The ranking signal — shown only implicitly via sort order |

### D. Visualization stubs in the UI

- **2D structure panel** — shows a decorative SVG hexagon grid. No actual molecule rendering (no RDKit SVG, no JSME, no Ketcher integration).
- **"Send to MPO" button** — no onClick handler wired.
- **"3D View" button** — no onClick handler; no NGL Viewer integration.
- **Sort button** — UI exists but callback is empty.

---

## Scope of Improvement (Prioritized)

### Tier 1 — Critical: fix the broken pipeline first

1. **Implement `run_state.insert_candidate()`** (~20 lines in `src/db/run_state.py`)
   Signature from usage: `insert_candidate(db, run_id, symbol, phase, kind, candidate_id, name, smiles, score, rank, passed, evidence)`

2. **Implement `GET /api/runs/{run_id}/candidates` endpoint** (~15 lines in `src/api/main.py`)
   Response: `{ candidates: ApiCandidate[] }` queried from `candidates` table filtered by `run_id`

These are shared with Phases 4, 6, 7 — implementing them once fixes all downstream phases.

### Tier 2 — High value, low effort (wire existing data)

3. **Show ADMET flags per candidate**
   Add a small badge row under each candidate card: hERG (color-coded: green/amber/red), AMES (neg=green/pos=red), BBB (pos/neg). All in `subscores.admet`.

4. **Show the LLM narrative**
   Display `subscores.narrative` as a collapsible panel in the candidate detail view. This is the most interpretable output of Phase 5.

5. **Show `admet_score` and `combined_pre8` explicitly**
   Replace the implicit sort with visible score columns. Show `admet_score` alongside vina — it carries 25% of the ranking weight.

6. **Show `passed` flag**
   Candidates that passed the combined gate deserve a visual distinction from borderline ones. One boolean field.

7. **Show novelty**
   Display `1 − tanimoto_to_approved` as a "Novelty" score. Researchers care deeply about IP novelty.

### Tier 3 — Richer UI

8. **Real 2D structure rendering** — Use RDKit-JS or a SMILES-to-SVG service to render actual molecule structures instead of the hexagon placeholder.

9. **ADMET detail panel** — Expandable section showing all ADMET endpoint values with pass/fail icons and the `disqualifying` + `concerns` lists.

10. **Wire sort button** — Sort by combined_pre8, admet_score, vina, novelty — the options already make sense given the computed fields.
