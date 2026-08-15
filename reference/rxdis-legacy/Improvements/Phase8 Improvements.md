# Phase 8 — In-Silico Validation Gate: Rationale, Gaps & Improvement Scope

## Scientific Rationale

Phase 8 answers: **"Of all the candidates generated across phases 4–7, which have confirmed computational binding evidence and drug-like properties sufficient to recommend for wet-lab synthesis?"**

It is the final computational gate before physical work begins. A candidate that passes Phase 8 is explicitly recommended for synthesis and assay.

**Validation approach:**
1. **Candidate gathering** — Priority: Phase 7 Pareto front > Phase 4 repurposing > all DB candidates. Top-5 per target.
2. **High-exhaustiveness re-docking** — Vina at exhaustiveness=12 (vs. 4 in earlier phases), three independent runs to measure pose stability.
3. **6-axis scorecard** — Weighted combination of binding affinity, pose stability, ADMET/developability, selectivity, novelty, and modality alignment.
4. **Pass gate** — combined_score ≥ 0.45.
5. **LLM medicinal chemist brief** — For passed candidates: 4-sentence synthesis brief covering why the candidate is promising, strengths, risks, and recommended first experiment.

**The 6-axis scorecard:**

| Axis | Weight | Computation |
|---|---|---|
| Binding affinity | 30% | `_norm_vina(vina_score)` — normalized to [0,1] with −10.0 kcal/mol ceiling |
| Pose stability | 20% | CV across 3 Vina runs → `1.0 − (cv − 0.05) / 0.25`; consistent binding pose = high stability |
| ADMET/Developability | 20% | `admet_score` (SM) or `developability_score` (biologics); neutral 0.5 if missing |
| Selectivity | 15% | Penalizes hERG high (0.5), medium (0.8), explicit off-target flags (0.3) |
| Novelty | 10% | `1.0 − max_tanimoto_to_approved` |
| Modality alignment | 5% | 1.0 if kind matches Phase 3 routing; 0.5 if mismatch |

**Pass threshold: 0.45** (combined weighted score)

---

## What Information Is Incomplete / Missing from the UI

### A. Phase 8 has no dedicated UI view

Phase 8 is mapped to the same view as Phase 9 (`Phase9Packaging.tsx`) in `App.tsx`. There is no standalone Phase 8 visualization. The validation gate — the final computational decision on which candidates advance — is entirely invisible to the user.

### B. Hardcoded/fake values in the combined Phase 8/9 view

| UI Element | What it shows | Reality |
|---|---|---|
| Attrition funnel "Phase 1 Targets" | 1,442 (if P1 complete, else 0) | Hardcoded constant — not read from DB |
| Attrition funnel "Validated Targets" | 142 (if P2 complete, else 0) | Hardcoded constant — not read from DB |
| Compliance: "ADMET Profile ✓" | Pass if `smCount > 0` | Checks for any SM candidate existing; does not check actual ADMET scores |
| Compliance: "Toxicity Screen ✓" | Pass if `completedPhases >= 7` | Phase count check — not actual toxicity results |
| Compliance: "hERG Liability ✓" | Pass if `topLeads.length > 0` | Checks for any lead existing; not actual hERG values |
| Compliance: "Mutagenicity (Ames) ✓" | Pass if `isComplete` | Binary run completion; not actual AMES results |
| Compliance: "Regulatory (ICH M7) ✓" | Pass if `isComplete` | Same — binary completion check |

### C. Data computed but never displayed

| Backend field | What it is | Why it matters |
|---|---|---|
| `binding_affinity` subscore | Normalized Vina from triple re-dock | The highest-exhaustiveness docking result in the entire pipeline — more reliable than earlier docking |
| `pose_stability` subscore | CV across 3 Vina runs | A *unique* Phase 8 signal not available anywhere else — consistent binding pose indicates a real binding mode, not a docking artifact |
| `admet_or_developability` subscore | ADMET (SM) or developability (biologic) | Axis 3 of the gate — hidden |
| `selectivity` subscore | Off-target and hERG penalty | Axis 4 — hidden |
| `novelty` subscore | 1 − tanimoto_to_approved | Axis 5 — hidden |
| `modality_alignment` subscore | Kind vs. Phase 3 routing match | Axis 6 — hidden |
| `passed` (boolean) | Whether combined_score ≥ 0.45 | The most important binary decision in the pipeline — not surfaced |
| `final_rank` | Ranking after Phase 8 re-scoring | The definitive candidate ranking — hidden |
| `candidate_brief` | LLM medicinal chemist synthesis recommendation | The most actionable Phase 8 output — 4 sentences for experimental planning |
| `target_validation_score` | Mean combined_score per target | Target-level summary of Phase 8 result |
| Triple Vina raw scores | `vina_runs: [score1, score2, score3]` | The raw data for pose stability — useful for assessing reproducibility |

### D. Compliance panel is scientifically misleading

The compliance checklist shows green checkmarks for ADMET, hERG, AMES, and ICH M7 based purely on whether runs completed and candidates exist — not on actual assay results. This creates false confidence. A run where all candidates have AMES-positive mutagenicity alerts would still show "Mutagenicity (Ames) ✓".

---

## Scope of Improvement (Prioritized)

### Tier 1 — Create a Phase 8 view (currently nonexistent)

1. **Build a dedicated Phase 8 validation view**
   Phase 8 is architecturally the most important phase — it makes the synthesis go/no-go recommendation. It should have its own view, not be silently merged into packaging. The view should:
   - Show a table of candidates with `final_rank`, `combined_score`, `passed` status, and the 6 subscores
   - Clearly distinguish passed (≥0.45) from failed candidates
   - Show the `candidate_brief` LLM text per passed candidate

2. **Show the 6-axis scorecard per candidate**
   Render `binding_affinity`, `pose_stability`, `admet_or_developability`, `selectivity`, `novelty`, `modality_alignment` as a radar chart or horizontal bar breakdown. This is the most scientifically informative view in the entire pipeline.

3. **Show `pose_stability` explicitly**
   This is a unique Phase 8 signal — the only phase that runs triple-dock and measures consistency. A simple "Pose stable: Yes/No" or a stability score number should be visible.

4. **Show `candidate_brief`**
   The LLM medicinal chemist brief is the most actionable Phase 8 output. It should appear in the candidate detail panel, replacing the generic compliance text.

### Tier 2 — Fix the packaging/summary view

5. **Replace hardcoded attrition funnel numbers with real DB counts**
   "Phase 1 Targets" = actual count from `targets` table. "Validated Targets" = count where `validation_score > 0`. "De Novo Generated" = count from `candidates` table by kind. All queryable from existing DB.

6. **Replace fake compliance checklist with real metric checks**
   - "ADMET Profile ✓" → pass if no candidate has `admet.disqualifying` entries
   - "hERG Liability ✓" → pass if no candidate has `admet.hERG = high`
   - "Mutagenicity (Ames) ✓" → pass if no candidate has `admet.AMES = pos`
   These are all in `subscores.admet` — one field read each.

7. **Add `passed` count to the final leads summary**
   "7 candidates screened, 4 passed Phase 8 gate (combined_score ≥ 0.45)" — a single sentence of actual output.

### Tier 3 — Scientific visualization

8. **Triple-dock consistency plot**
   Show the three Vina scores per candidate as a dot plot with range bar. Wide range = unstable pose (artifact); tight cluster = reliable binding mode. This is the most distinctive Phase 8 visualization.

9. **Binding affinity histogram**
   Distribution of all screened candidates' Vina scores, with the −7.0 kcal/mol threshold marked. Contextualizes where the passed candidates sit relative to the full screened set.

10. **Phase 8 vs. Phase 5/6 score delta**
    Compare each candidate's Phase 8 `combined_score` to its earlier score from Phase 5 or 6. Candidates that score significantly higher under high-exhaustiveness re-docking are more trustworthy hits.
