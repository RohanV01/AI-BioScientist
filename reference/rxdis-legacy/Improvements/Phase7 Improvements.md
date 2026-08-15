# Phase 7 — Multi-Parameter Optimization (MPO): Rationale, Gaps & Improvement Scope

## Scientific Rationale

Phase 7 answers: **"Which candidates achieve the best simultaneous balance across multiple competing drug-likeness objectives?"**

Drug optimization is inherently multi-objective: improving potency often hurts solubility; reducing immunogenicity can reduce activity. Phase 7 uses **multi-objective Bayesian optimization with active learning** to navigate this tradeoff space rigorously.

**Pipeline:**
1. **Builds a candidate pool** from Phase 5 (small molecules) and Phase 6 (biologics)
2. **Fits Gaussian Process (GP) surrogates** — one independent GP regressor per objective (sklearn GP, RBF + WhiteKernel), separately for each target
3. **Computes the Pareto front** — set of candidates not dominated by any other (better on all objectives simultaneously)
4. **Computes hypervolume** — scalar measure of Pareto front quality (how much of the objective space is covered)
5. **Suggests new candidates** via Upper Confidence Bound (UCB, β=2.0) — trades off exploration vs. exploitation
6. **Re-evaluates suggestions** — SM: re-ADMET + preserve vina_norm; Biologics: re-developability scoring
7. **Generates new pool** — SM: BRICS analog enumeration from Pareto seeds; Biologics: single-residue mutations
8. **Convergence check** — stops when hypervolume improvement <1%, or at 5 iterations, or budget exhausted

**Objectives:**

| Modality | Objectives | Desirability weights |
|---|---|---|
| Small molecule | `potency` (vina_norm), `admet_score`, `novelty` | 0.40 / 0.30 / 0.30 |
| Biologic | `developability_score`, `novelty_bio` (fixed=1.0) | 0.60 / 0.40 |

**Featurization for GPs:**
- SM: Morgan fingerprints (radius=2, 2048-bit) with physchem descriptor fallback
- Biologic: one-hot amino acid encoding (60 AA × 20 = 1,200 features)

---

## What Information Is Incomplete / Missing from the UI

### A. The Pareto frontier chart is entirely fake

The centrepiece visualization of Phase 7 — the Pareto frontier scatter plot — is built from a hardcoded constant array:

```typescript
const FRONTIER = [
  { admet: 0.10, potency: 9.8 },
  { admet: 0.18, potency: 9.4 },
  ...
  { admet: 1.00, potency: 0.4 },
];
```

This has no connection to the actual Phase 7 output. The real Pareto front (`optimized[symbol].pareto_front`) is never read or plotted.

### B. Hardcoded fallback formulas for missing subscores

When real subscores are absent, the UI uses arithmetic fallbacks that produce plausible-looking but fabricated values:

| UI Field | Fallback formula | What's wrong |
|---|---|---|
| Vina Score | `c.combined_score × −12` | Multiplying a 0–1 score by −12 to fake kcal/mol |
| GNINA (CNN) | `0.95 − i × 0.025` | Descends from 0.95 → ~0.67 by row index — pure fabrication |
| RMSD to Ref | `1.2 + i × 0.3` | Ascends from 1.2 → 3.4 Å by row index — pure fabrication |
| "Lead" badge | `c.combined_score ≥ 0.7` | Hardcoded 0.7 threshold; Phase 7 has its own `pareto_rank` |

### C. Critical blockers (shared with P4, P5, P6)

Phase 7 calls `_update_candidates_db()` which updates existing rows — so it is partially less broken than earlier phases. But:
- If Phase 5/6 never inserted the rows (because `insert_candidate()` is missing), Phase 7 has nothing to update.
- The `GET /api/runs/{run_id}/candidates` endpoint is still missing, so even updated rows cannot be fetched.

### D. Data computed but never displayed

| Backend field | What it is | Why it matters |
|---|---|---|
| `pareto_rank` | 1–20 ranking within the Pareto front | The definitive Phase 7 ranking — more meaningful than `combined_score` alone |
| `desirability` | Weighted scalar across objectives (0–1) | The actual ranking signal; currently invisible |
| `potency` | Re-evaluated vina_norm | Objective 1 for SM — hidden |
| `admet_score` | Re-evaluated ADMET | Objective 2 for SM — hidden |
| `novelty` | 1 − max_tanimoto | Objective 3 for SM — hidden |
| `developability_score` | Re-evaluated developability | Objective 1 for biologics — hidden |
| `hypervolume_final` | Final Pareto front volume per target | The convergence metric; tells you how well the optimization ran |
| `iterations_run` | Number of active learning iterations | Convergence indicator — did it converge early or hit the 5-iteration cap? |
| `n_evaluated_total` | Total candidates evaluated in the AL loop | Scale indicator for the optimization effort |
| GP uncertainty estimates | (mean, std) per candidate per objective | Standard deviation = exploration uncertainty — useful for "most uncertain" candidates |
| LLM iteration review | Advisory notes from LLM gate per iteration | Logged to `decisions` table, never surfaced |

---

## Scope of Improvement (Prioritized)

### Tier 1 — Critical blockers (shared with P4, P5, P6)

1. **Implement `run_state.insert_candidate()`** — rows must exist before Phase 7 can update them
2. **Implement `GET /api/runs/{run_id}/candidates`** — fetching is blocked without this endpoint

### Tier 2 — Replace fake visualizations with real data

3. **Replace the hardcoded FRONTIER array with real Pareto front data**
   Read `optimized[symbol].pareto_front`, extract `(admet_score, potency)` pairs for SM or `(developability_score, novelty_bio)` for biologics, and plot actual points. This is the single most important visualization fix in Phase 7.

4. **Add Pareto rank and desirability columns to the table**
   Replace "GNINA" and "RMSD to Ref" (which Phase 7 doesn't compute) with `pareto_rank` and `desirability` — the actual Phase 7 output fields.

5. **Show the three objective scores per candidate**
   Add `potency`, `admet_score`, `novelty` columns (SM) or `developability_score` column (biologics). These are the axes of the optimization — hiding them defeats the purpose of Phase 7.

6. **Remove the fabricated GNINA and RMSD values**
   Phase 7 does not compute GNINA or RMSD. These columns should either be removed or replaced with real Phase 7 fields.

### Tier 3 — Scientific depth

7. **Show hypervolume convergence curve**
   Plot hypervolume at each iteration — a flat curve means the optimization converged quickly; still-rising means the budget was exhausted. This is the key diagnostic for Bayesian optimization quality.

8. **Show `iterations_run` and `n_evaluated_total`**
   Simple metadata: "Converged in 3 iterations, 247 candidates evaluated." Tells the user how hard the optimizer worked.

9. **Show GP uncertainty for top candidates**
   Candidates with high GP uncertainty are worth re-synthesizing — they could be better than predicted. A simple error bar or "uncertainty" column on the Pareto plot would communicate this.

10. **Biologics-specific Pareto view**
    When candidates are biologics, the axes should be `developability_score` vs. `novelty_bio`, not the SM axes. Currently there is no conditional rendering for the biologic case.
