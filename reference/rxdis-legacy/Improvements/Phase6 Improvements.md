# Phase 6 — Biologics / Peptide Design: Rationale, Gaps & Improvement Scope

## Scientific Rationale

Phase 6 answers: **"For targets routed to the biologic branch, can we design novel peptide binders with favorable developability properties?"**

It runs a structure-informed de novo peptide design pipeline:

1. **6.1 Interface context extraction** — Analyzes target structure (PDB), binding pockets (fpocket), hotspot residues (AlphaMissense variants + LLM gate), essentiality, and localization to determine the design strategy:
   - `cyclic_peptide` — intracellular targets, hard-to-drug pockets
   - `antibody_epitope` — extracellular/membrane targets
   - `helical_mimetic` — helical interface mimicry
   - `stapled_peptide` — disordered/flexible targets

2. **6.2 Sequence generation** — Three-tier ladder:
   - **Tier 1**: RFdiffusion (structure-based backbone diffusion)
   - **Tier 2**: ProteinMPNN (sequence design on diffused backbone)
   - **Tier 3**: LLM fallback (sequence completion via language model)
   - Sequences validated: 8–60 amino acids, no stop codons, canonical AA only

3. **6.3 Refolding validation (ipTM gate)** — Optional Boltz-1 CPU refolding against target PDB. Computes ipTM (interface predicted TM score, 0–1), PAE interface (Å), and per-chain pLDDT. Borderline sequences (ipTM 0.65–0.75) are triaged by LLM gate.

4. **6.3 Developability assessment** — Four axes:
   - Aggregation propensity (charge/hydrophobicity balance)
   - Solubility score
   - Immunogenicity (MHC-II proxy: count of 9-mer windows with ≥3 hydrophobic anchors, or NetMHCpan if available)
   - Stability (half-life class, N-terminal rule, proteolysis concern)

5. **6.4 LLM immunogenicity gate** — For top-3 candidates: LLM assesses clinical acceptability and recommends de-immunization modifications.

**Combined scoring:**
- If ipTM available: `0.50 × (ipTM / 0.9) + 0.50 × developability_score`
- If ipTM unavailable: `developability_score` (Boltz-1 CPU may time out)

**Pass gate:** `len(disqualifying) == 0 AND (ipTM > 0.70 if available)`

---

## What Information Is Incomplete / Missing from the UI

### A. Hardcoded fallback values that mask real data

The UI uses a `subscore(candidate, key, fallback)` helper. When subscores are missing, hardcoded defaults are displayed as if they were real computed values:

| UI Field | Fallback shown | Reality |
|---|---|---|
| Expression Yield | 8.14 mg/L | Not computed — no expression yield model exists |
| Thermal Stability | 74.2 °C | Not computed — stability is a class (low/medium/high), not °C |
| Aggregation Risk | 12.4% | Real value exists as "low/medium/high" string, not a % |
| Isoelectric Point (pI) | 2.1 | Not computed |
| Humanization % | 94.4% | Not computed |

These values are always the hardcoded defaults because `insert_candidate()` is missing (see section B). Users see fake numbers.

### B. Critical blockers — data never persists or loads

**1. `run_state.insert_candidate()` does not exist**
Phase 6 `runner.py` calls this at line 481. Without it, all Phase 6 candidates are discarded after execution.

**2. `GET /api/runs/{run_id}/candidates` endpoint does not exist**
The frontend cannot retrieve any Phase 6 results. Both blockers are shared with Phases 4, 5, 7.

**3. `evidence` ≠ `subscores` mapping mismatch**
Phase 6 runner stores results in an `evidence` dict but the UI expects a `subscores` dict. The keys don't match — even if persistence were fixed, `expression_yield`, `thermal_stability`, etc. would still not exist because Phase 6 doesn't compute them.

### C. Data computed but never displayed

| Backend field | What it is | Why it matters |
|---|---|---|
| `iptm` | Boltz-1 structural binding score (0–1) | Primary binding validation metric for peptides — equivalent to Vina for small molecules |
| `pae_interface` | Interface predicted aligned error (Å) | Lower = more confident binding interface prediction |
| `binder_plddt` | Per-chain structural confidence | Quality of the computational structure prediction |
| `refolding_source` | Where ipTM came from | `boltz1_local_cpu` or None — distinguishes validated from unvalidated sequences |
| `design_strategy` | cyclic/antibody_epitope/helical/stapled | The most informative single descriptor of the peptide's intended mechanism |
| `target_class` | extracellular/membrane/intracellular/disordered | Drives the design strategy; informative for the biologist |
| `type` | cyclic_peptide vs linear_peptide | Affects formulation and synthesis complexity |
| `length` | Sequence length in amino acids | Short (8–15) vs long (30–60) peptides have very different properties |
| `stability` dict | `{half_life_class, n_terminal_rule, proteolysis_concern}` | Half-life class (short/medium/long) and proteolysis concerns are critical for peptide drugs |
| `disqualifying` | List of hard failures | e.g. `["aggregation_high(score=0.85)"]` — the reason a candidate failed |
| `concerns` | Non-fatal warnings | Context for borderline candidates |
| `immunogenicity_report` | LLM 6.4 de-immunization recommendations | Computed for top-3 candidates but never persisted to DB and never shown |
| `n_mhc_strong_binders` | Count of 9-mer windows with MHC-II anchors | Quantitative immunogenicity estimate |
| `solubility_score` | Float 0–1 | More informative than string label; useful for ranking |

### D. Hotspot display is fake

The UI colors certain amino acids as "hotspots" using a client-side heuristic (`i % 7 === 0 || 'KRH'.includes(aa)`). The LLM-selected hotspot residues computed in step 6.1 are never sent to the frontend.

---

## Scope of Improvement (Prioritized)

### Tier 1 — Critical: fix the broken pipeline (shared with P4, P5, P7)

1. **Implement `run_state.insert_candidate()`** — shared fix that unblocks all phases
2. **Implement `GET /api/runs/{run_id}/candidates`** — shared fix for all downstream phases
3. **Fix `evidence` → `subscores` mapping** — Phase 6 populates `evidence`, UI reads `subscores`. Either rename the dict or add a mapping layer in the persistence function.

### Tier 2 — Remove fake fallbacks, show real data

4. **Replace fake property columns with real ones**
   - Remove "Expression Yield (mg/L)", "Thermal Stability (°C)", "Humanization %" — these are not computed
   - Replace with actual fields: `iptm`, `aggregation` (low/medium/high), `immunogenicity` (low/medium/high), `design_strategy`, `length`

5. **Show ipTM prominently**
   For peptides, ipTM is the structural binding score equivalent to Vina for small molecules. It should be the primary validation metric shown per candidate, not buried.

6. **Show design_strategy as a badge**
   "Cyclic Peptide / Helical Mimetic / Stapled / Antibody Epitope" — this is the most informative single descriptor of what the candidate is.

7. **Show stability flags**
   Display `half_life_class` (short/medium/long) and `proteolysis_concern` (yes/no) — directly relevant to whether a peptide drug is viable.

8. **Show disqualifying + concerns lists**
   Similar to ADMET flags in Phase 5, these are the explicit reasons candidates passed or failed.

9. **Show immunogenicity_report**
   Persist and display the LLM 6.4 immunogenicity assessment + de-immunization suggestions for top candidates.

### Tier 3 — Structural depth

10. **Replace fake hotspot logic with backend-computed hotspots**
    The LLM-selected hotspot residues from step 6.1 should be persisted in the evidence dict and used to drive the sequence coloring.

11. **Show pae_interface alongside ipTM**
    "ipTM 0.78, PAE 3.2 Å" together give a much clearer picture of binding confidence than ipTM alone.

12. **Peptide 3D viewer**
    If Boltz-1 generated a structure (pdb URL in evidence), an NGL Viewer rendering would be directly analogous to what Phase 2 shows for target structures.
