# Phase 2 — Target Validation: Rationale, Gaps & Improvement Scope

## Scientific Rationale

Phase 2 answers: **"Of the candidate targets from Phase 1, which are actually druggable — and by what modality?"**

It takes the ranked gene list and runs a multi-axis druggability assessment: does the protein have a detectable binding pocket? Is it expressed in the right tissues? Is it structurally well-characterized? Is there existing chemical matter? Does essentiality create a toxicity risk?

**Why this matters after Phase 1:**
Phase 1 is purely biological (PU learning on omics). It can rank KRAS highly — but whether you can drug KRAS with a small molecule, antibody, or PROTAC is a completely separate question that requires structural biology, expression profiling, and chemical precedent data. Phase 2 answers that.

**The 7-feature validation model:**

| Feature | Source | Weight / Role |
|---|---|---|
| `tractability` | Max modality score across SM/AB/PROTAC/peptide/oligo | Primary druggability signal |
| `structure` | AlphaFold pLDDT / 100 | Confidence in 3D model used for pocket detection |
| `essentiality` | DepMap Chronos median (cancer-indication adjusted) | Core-essential genes penalized for safety risk |
| `genetic` | From Phase 1 evidence trail | Human genetic validation |
| `ppi_centrality` | STRING network centrality from Phase 1 | Network hub context |
| `variant_support` | AlphaMissense high-pathogenicity missense count | Functional constraint evidence |
| `safety` | 0.5 × TSI + 0.5 × (1 − critical_tissue_flag) | Expression safety (heart/brain/kidney/liver) |

**Modality decision logic:**
- **Small molecule**: pocket druggability ≥0.5 → high SM score
- **Antibody**: membrane/extracellular targets → high AB score
- **PROTAC**: intracellular + oncology-essential → PROTAC-eligible; suppressed if good SM pocket exists
- **Peptide**: extracellular, no SM pocket
- **Oligo**: intracellular, poor druggability

**Pass threshold**: validation_score ≥ 0.5 (seeded targets always pass; floor lowers to 0.3 if < 3 non-seeded targets would pass)

---

## What Information Is Incomplete / Missing from the UI

### A. Hardcoded fake values (not real data)

These show real-looking numbers but are constants in the source code:

| UI Element | What it shows | Reality |
|---|---|---|
| "Active Cohorts: 04" | Stats bento | Hardcoded `"04"` |
| "ML Confidence (avg): 89.4%" | Stats bento | Hardcoded `"89.4%"` |
| "Routing Queue: Batch 12-B Processing 78%" | Stats bento | Hardcoded `"78%"` |
| "AlphaFold v2.0" badge | Table header | Hardcoded string |
| "Pocket_Druggable_V4" badge | Table header | Hardcoded string |
| H-Bonds: 12 | Inspector → Viewer tab | Hardcoded constant |
| Hydrophobic: 28 | Inspector → Viewer tab | Hardcoded constant |
| Pocket Vol: 450 Å³ | Inspector → Viewer tab | Hardcoded constant |
| Druggability: 0.82 | Inspector → Viewer tab | Hardcoded constant |
| Evidence log entries | Inspector → Logs tab | Hardcoded fake timeline |

### B. Real data computed but never displayed

| Backend Field | Where computed | Why it matters |
|---|---|---|
| `evidence_summary` | `scoring.py` `generate_narrative()` | LLM or deterministic summary of *why* a target passes — most interpretable output of Phase 2, never shown |
| `attributions` dict | `scoring.py` `compute_validation_score()` | Per-feature contributions (∑=1.0) — the real Phase 2 SHAP equivalent |
| Full pocket list (up to 5 pockets) | `pockets.py` | Each pocket has druggability, volume, coordinates, strategy (active_site/allosteric) — only max_druggability is shown |
| `essentiality` details | `essentiality.py` | `chronos_median`, `essential_in_n_lines`, `is_core_essential`, `high_tox_flag` — safety-critical data |
| `variants` details | `variants.py` | `am_mean_pathogenicity`, `am_high_path_fraction`, `high_path_missense` — mutational constraint |
| `localization` | `localization.py` | Subcellular compartment (intracellular/membrane/secreted) — directly drives modality |
| `safety` | `expression.py` | `tsi`, `critical_tissue_flag`, `specific_tissues`, `broadly_expressed` — on-target toxicity risk |
| `n_bioactive`, `n_potent`, `max_phase` | `chembl.py` | Chemical matter precedent — how many known compounds, what clinical stage |
| `modality_scores` (all 5 modalities) | `tractability.py` | Full score breakdown (SM/PROTAC/AB/peptide/oligo) — only primary + secondary stored |
| `passed` flag | `runner.py` | Whether the target cleared the threshold — not surfaced per-row in UI |

### C. Structural / viewer stubs

- **3D protein viewer** (Inspector → Viewer tab): placeholder text "Integrate NGL Viewer here." The backend *does* acquire a real PDB file (AlphaFold → RCSB → ESMFold waterfall) with a URL in `evidence_trail.phase2.structure.pdb_url` — but nothing loads it.
- **SMILES column**: always empty string `''`. No SMILES is fetched anywhere in Phase 2.

### D. SHAP tab logic bug

The Inspector's SHAP bar extraction reads all numeric values from the entire `evidence_trail` object instead of from `evidence_trail.phase2.attributions`. This means the bars either show Phase 1 omics values or nothing meaningful — the real 7-feature Phase 2 attributions are never rendered.

```typescript
// Current (wrong): slices any numeric field from the whole trail
const shapBars = Object.entries(trail)
  .filter(([, v]) => typeof v === 'number')
  .slice(0, 6)

// Should be:
const attributions = trail?.phase2?.attributions  // {tractability, structure, essentiality, ...}
```

### E. AI rationale text is still the Phase 1 static template

The Inspector "AI Rationale" paragraph is the same hardcoded string from Phase 1 — it doesn't use `evidence_trail.phase2.evidence_summary` (which contains the actual LLM or deterministic narrative computed by the backend).

---

## Scope of Improvement (Prioritized)

### Tier 1 — Low effort, high signal (data in DB, just not wired to UI)

1. **Fix SHAP attribution extraction bug**  
   One-line fix: point to `evidence_trail.phase2?.attributions` instead of iterating the whole trail object. This immediately makes the SHAP bars scientifically correct for Phase 2.

2. **Show `evidence_summary` as the AI Rationale text**  
   Replace the hardcoded paragraph with `evidence_trail.phase2?.evidence_summary`. The backend already writes a plain-English explanation of why the target passed/failed.

3. **Show full modality score breakdown in Inspector**  
   All 5 modality scores (SM/PROTAC/AB/peptide/oligo) are computed. Surface them as a small horizontal bar chart in the SHAP tab — this is the most actionable output of Phase 2.

4. **Show `localization` compartment as a badge per row**  
   "Intracellular / Membrane / Secreted" directly informs the biologist which modalities make sense. One field read.

5. **Remove hardcoded stats bento values**  
   Replace with: actual n_validated / n_passed counts (from `phase_results` table), actual mean validation score, actual pass threshold used.

6. **Show `passed` flag per row**  
   Add a clearer "Pass / Fail" indicator tied to the real `passed` boolean in `evidence_trail.phase2`, not just the threshold-based "Validated/Processing/Insignificant" label derived from score alone.

### Tier 2 — Medium effort, meaningful completeness

7. **Essentiality + safety panel in Inspector**  
   Show `chronos_median`, `is_core_essential`, `critical_tissue_flag`, `specific_tissues` together as a "Safety Flags" card. This is the most important risk signal for go/no-go.

8. **Pocket list panel**  
   Instead of just `max_druggability`, show a small table of all detected pockets (up to 5) with druggability, volume, and strategy (active_site/allosteric). Allosteric pockets are scientifically interesting and currently invisible.

9. **Chemical matter card**  
   Show `n_potent` / `n_bioactive` / `max_phase` from ChEMBL. "47 bioactive compounds, 12 potent (pIC50 ≥ 6), max phase 2" — this alone heavily influences SM tractability decisions.

10. **Variants card in Inspector**  
    Show `high_path_missense`, `am_mean_pathogenicity`, `am_high_path_fraction` as a "Mutational Constraint" panel — directly affects whether PROTAC/covalent inhibitor approaches are feasible.

### Tier 3 — Higher effort, requires frontend/backend work

11. **Real AlphaFold 3D viewer (NGL Viewer)**  
    The `pdb_url` is already in the evidence trail. NGL Viewer loads directly from a URL in-browser — this is mostly a frontend integration task. Replace the hardcoded pocket stats with real fpocket output (pocket volume, druggability score per pocket).

12. **Tissue expression heatmap**  
    `specific_tissues` from HPA contains tissue-level nTPM values. A small heatmap (top 10 tissues) would replace the "[Visualization Loading…]" card in Phase 1 and be directly accessible from Phase 2 data.

13. **Modality comparison radar chart**  
    Plot all 5 modality scores as a radar/spider chart — gives an instant visual of whether a target is "clearly SM", "ambiguous SM/PROTAC", etc.

---

## Recommended First Pass

**Tier 1 items 1–6** require only frontend changes (fixing the attribution extraction bug, reading the right fields from the evidence trail, removing hardcoded constants). These turn Phase 2 from a view that shows 3 real columns + many fakes into one that accurately represents the multi-axis druggability assessment the backend already computed.

The biggest single win is item 2: the `evidence_summary` field contains the most interpretable output of the entire Phase 2 pipeline and is currently displayed nowhere.
