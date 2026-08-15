# Phase 3 & 4 — Routing & Drug Repurposing: Rationale, Gaps & Improvement Scope

---

## PHASE 3 — Modality Routing

### Scientific Rationale

Phase 3 answers: **"For each validated target, which therapeutic modality is most tractable — and which downstream development branch should it enter?"**

It takes Phase 2 validated targets and runs a rule engine that:
1. **Refines modality scores** — applies a final safety penalty (critical tissue expression → −12% SM score) on top of Phase 2 modality probabilities
2. **Classifies repurposing priority** — maps clinical stage to HIGH / MEDIUM / LOW_CLINICAL / LOW tiers based on OpenTargets tractability + ChEMBL max_phase
3. **Assigns branches** — based on the `intent_mode` config (repurpose / de_novo / explore), routes each target to one or more of: `P4_repurpose`, `P5_small_molecule`, `P6_biologic`

This is a pure decision layer — no new data is fetched. It acts on everything Phase 2 computed.

**Branch assignment logic by intent:**

| Intent Mode | Branches assigned |
|---|---|
| `repurpose` | P4 only |
| `de_novo` | P5 (SM/PROTAC) OR P6 (AB/peptide) — no P4 |
| `explore` | P4 + primary de novo branch + secondary (if score high enough) |

---

### What Information Is Incomplete / Missing from the UI

#### A. Data computed but never displayed

| Backend Field | What it is | Why it matters |
|---|---|---|
| `modality_secondary` | Second-best modality | Biologists often want optionality — a target with strong SM + decent AB scores offers a backup strategy |
| Full modality scores dict | SM/PROTAC/AB/peptide/oligo scores (0–1) | Only primary is shown; the score gap between primary and secondary indicates confidence |
| `repurposing_priority` | HIGH / MEDIUM / LOW_CLINICAL / LOW | Directly predicts how fast Phase 4 repurposing can yield a clinical candidate |
| `branches` list | Which phases the target enters (P4/P5/P6) | Not surfaced anywhere in the UI — biologist can't see the routing decision |
| Safety penalty applied | Whether SM score was penalized for critical tissue | Critical context for understanding why a pocket-drugable target was routed to AB instead |

#### B. Visualization stubs

The **Sankey diagram** in the Phase 3 view shows hardcoded SVG flow lines — the connections are not driven by the actual routing data. A target's true routing path (target → modality → branch) is not represented.

#### C. Missing implementation (critical bug)

**`route_target()` function does not exist.** It is imported and called in `runner.py` but is not defined in `rule_engine.py`. Phase 3 will throw an `ImportError` on first execution. The function needs to orchestrate `score_modalities()` + `compute_repurposing_priority()` + `apply_intent_routing()` into a single result dict.

---

### Scope of Improvement

#### Tier 1 — Low effort (data exists, just not shown)

1. **Show branch assignment per target** — Add a "Branches" column or badge row showing P4 / P5 / P6 assignments. This is the primary output of Phase 3 and is currently invisible.

2. **Show modality_secondary** — Add a secondary modality chip next to the primary. Even "(AB, 0.61)" conveys optionality at a glance.

3. **Replace hardcoded Sankey with data-driven flows** — The target → modality → branch routing is fully computable from the existing data. The Sankey should show real flow volumes, not fixed SVG lines.

4. **Show repurposing priority badge** — HIGH / MEDIUM / LOW_CLINICAL badge per target directly communicates how actionable Phase 4 will be for that target.

#### Tier 2 — Medium effort

5. **Implement `route_target()`** — Wire together the three rule_engine functions that already exist. This is the missing glue function (~30 lines) that would make Phase 3 actually execute.

6. **Show modality score breakdown** — Small bar chart of all 5 modality scores per target (SM/PROTAC/AB/peptide/oligo). The full score dict is already computed in `score_modalities()` but only primary is stored.

---

## PHASE 4 — Drug Repurposing

### Scientific Rationale

Phase 4 answers: **"For repurposable targets, which approved or known drugs are the best candidates — combining structural, clinical, transcriptomic, and knowledge-graph evidence?"**

It uses **4-signal triangulation**:

| Signal | Weight | Source | What it captures |
|---|---|---|---|
| **Docking** | 35% | AutoDock Vina 1.2.7 (local) | Structural complementarity between drug and binding pocket |
| **Clinical** | 30% | ChEMBL max_phase / 4 | Regulatory de-risking — approved drugs carry least development risk |
| **Transcriptomic** | 20% | LINCS L1000 / CLUE API | Whether the drug reverses the disease gene signature |
| **Knowledge Graph** | 15% | PrimeKG drug–protein edges | Curated mechanistic evidence |

**Why 4 signals?** Any single signal fails alone: docking misses flexibility, clinical stage ignores mechanism, LINCS is noisy, KG is incomplete. The triangulation catches candidates that score well on 2+ orthogonal signals.

**Pass criteria (B3 fix):** `score ≥ 0.30 AND (structural_evidence OR lincs_score ≥ 0.5)` — prevents purely clinical candidates (approved drug, no structural/LINCS support) from being called hits.

**Vina calibration (B2 fix):** The docking ceiling is set to the 95th percentile of actual scores per target (not a fixed −12 kcal/mol), so normalization is empirical and target-specific.

**Two-tier ligand library:**
- **Tier 1**: ChEMBL drugs with confirmed MOA for the target (high-accuracy docking, exhaustiveness=8)
- **Tier 2**: All FDA-approved compounds (exhaustiveness=4), pre-filtered by Morgan fingerprint similarity to Tier 1 hits to reduce from ~3,000 → ~800 compounds

---

### What Information Is Incomplete / Missing from the UI

#### A. Hardcoded fake values

| UI Element | What it shows | Reality |
|---|---|---|
| Radar chart axes (Selectivity, Toxicity, BBB, Solubility, hERG, Bioavailability) | Phase 4 subscore-like values | **Hardcoded defaults** — `sub.selectivity ?? 70`, `sub.safety ?? 65`, etc. These axes don't correspond to anything Phase 4 computes |
| Target Occupancy Simulation | Bar chart [35, 52, 68, 81, 89...] over time | **Completely hardcoded array** — not computed |

#### B. Real data computed but never displayed

| Backend Field | What it is | Why it matters |
|---|---|---|
| `vina_score` (kcal/mol) | Raw AutoDock Vina binding affinity | The primary docking result — scientists want to see the raw number |
| `vina_norm` | Calibrated 0–1 docking score | Shows where the drug sits in the per-target docking distribution |
| `clinical_score` | max_phase/4 (0–1) | Explicit clinical de-risking signal |
| `kg_score` | PrimeKG edge (1.0 direct / 0.5 family / 0.0) | Curated mechanistic link |
| `lincs_score` | Transcriptomic reversal strength (0–1) | Disease signature reversal evidence |
| `pass_mechanism` | "structural" / "transcriptomic" / "clinical" / "mixed" | Which signal drove the hit — critical for interpreting the result |
| `structural_evidence` | bool — whether vina ≤ −7.0 or KG > 0 | Required for pass; not shown |
| `weights_used` | Actual weight dict for this candidate | Weights vary (3-signal if LINCS unavailable) — should be shown |
| `mechanism_of_action` | ChEMBL MOA string (e.g. "GTPase KRas (G12C) covalent inhibitor") | Most informative single field for a repurposing candidate |
| `is_covalent_target` | bool | Covalent targets require covalent-warhead drugs — major selectivity concern |
| `covalent_note` | Explanation of covalent evidence | Context for the covalent flag |
| `borderline` | bool — score 0.15–0.30, marginal hit | Useful for "watch list" candidates |
| `source` | "chembl_mechanism" or "approved_library" | Tier 1 (known MOA) vs Tier 2 (screening hit) — very different confidence levels |
| `vina_ceiling_used` | Per-target calibrated docking ceiling | Shows the reference point for vina_norm |

#### C. Missing API endpoint (critical gap)

**`GET /api/runs/{run_id}/candidates` does not exist** in `src/api/main.py`. The frontend `useCandidates()` hook calls this endpoint — Phase 4 data cannot be displayed at all without it, even after a successful run.

#### D. Missing DB write function (critical gap)

**`run_state.insert_candidate()` does not exist** in `src/db/run_state.py`. Phase 4 runner calls this to persist results. Without it, Phase 4 output is lost after execution — nothing is stored.

#### E. The narrative is shown, but context is missing

`subscores.narrative` (LLM-generated rationale) is shown in the UI — this is good. But it appears without the supporting scores (Vina, LINCS, KG) that would let a biologist evaluate whether the narrative is well-supported.

---

### Scope of Improvement (Prioritized)

#### Tier 1 — Critical gaps that break Phase 4 entirely

1. **Implement `run_state.insert_candidate()`** — ~20 lines in `src/db/run_state.py`. Without this, all Phase 4 output is lost.

2. **Implement `GET /api/runs/{run_id}/candidates` endpoint** — ~15 lines in `src/api/main.py`. Without this, the frontend cannot load any Phase 4 data.

These two items are blockers — Phase 4 cannot function end-to-end without them.

#### Tier 2 — Replace fake UI with real data (data exists in subscores)

3. **Replace radar chart** — The 6 current axes (Selectivity, Toxicity, BBB, etc.) don't correspond to anything Phase 4 computes. Replace with the actual 4 signals: Docking (vina_norm), Clinical (clinical_score), Transcriptomic (lincs_score), KG (kg_score). These are the real radar axes and all exist in `subscores`.

4. **Show vina_score prominently** — The raw kcal/mol value (e.g. −8.67) is more interpretable to medicinal chemists than a normalized score. Show it alongside vina_norm.

5. **Show mechanism_of_action** — One of the most informative fields; currently invisible.

6. **Show source badge** — "Tier 1 (Known MOA)" vs "Tier 2 (Screening hit)" communicates confidence immediately.

7. **Show is_covalent_target flag** — A covalent warhead indicator is safety-critical and should be visible.

8. **Remove hardcoded occupancy simulation chart** — Replace with either nothing (honest) or actual per-signal score breakdown as a stacked bar.

#### Tier 3 — Enrichment for scientific depth

9. **Show pass_mechanism** — "This hit is structural" vs "this hit is transcriptomic-only" changes how a biologist interprets it. A badge ("Structural / Mixed / Clinical") is sufficient.

10. **Show borderline candidates** in a separate section — Candidates with score 0.15–0.30 are "watch list" material. Currently invisible.

11. **Show weights_used** — A tooltip showing the actual weight breakdown (e.g. "Docking 35% / Clinical 30% / LINCS 20% / KG 15%") makes the score interpretable.

12. **Add Vina calibration context** — "Docking score: −8.67 kcal/mol (95th percentile ceiling: −10.2 kcal/mol, Vina norm: 0.93)" would fully contextualize the docking result.

---

## Combined Phase 3–4 Summary

| Layer | Status | Biggest Gap |
|---|---|---|
| P3 backend (rule engine) | Logic exists but `route_target()` missing | Phase 3 won't run without implementing the missing glue function |
| P3 frontend | Shows modality buckets; Sankey is fake | Branch assignments and secondary modality scores never shown |
| P4 backend | Sophisticated 4-signal pipeline, fully implemented | `insert_candidate()` missing → output lost; `route_target()` missing → P3 blocks P4 |
| P4 frontend | Narrative shows (when data loads); radar + occupancy are hardcoded fakes | No API endpoint means Phase 4 data can't load at all |

**Highest ROI fixes in order:**
1. Implement `route_target()` (Phase 3 runner won't complete without it)
2. Implement `insert_candidate()` (Phase 4 output won't persist without it)
3. Add `GET /api/runs/{run_id}/candidates` endpoint (Phase 4 UI can't load without it)
4. Replace the fake radar chart with the real 4-signal axes (vina_norm, clinical_score, lincs_score, kg_score)
5. Surface `mechanism_of_action`, `source`, `is_covalent_target`, and `vina_score` in the candidate card
