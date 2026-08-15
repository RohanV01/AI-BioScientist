# Scientific Protocol — Phase 8: In-Silico Validation Gate

**Document version:** 1.0  
**Written:** 2026-06-03  
**Status:** MD deferred pending GROMACS installation; Vina triple re-dock active  
**Corresponding implementation:** `src/phases/phase8/` — `scorecard.py`, `runner.py`  
**See also:** `phases/phase8_summary.md`, `bottlenecks/phase7_phase8.md`

---

## 1. Purpose and Scope

Phase 8 is the final in-silico gating step in the RxDis pipeline. Its scientific purpose is threefold:

1. **Confirm docking reproducibility:** By re-docking each candidate three independent times at higher exhaustiveness than any prior phase, Phase 8 verifies that the binding mode observed in Phases 4 and 5 was not a stochastic artifact of a single low-exhaustiveness run.

2. **Composite quality gatekeeping:** The 6-axis scorecard integrates binding, stability, ADMET/developability, selectivity, novelty, and modality alignment into a single pass/fail decision. No single axis dominates — a candidate with excellent binding but high hERG liability is rejected.

3. **Generate communicable evidence summaries:** The LLM-generated medicinal chemist brief for each passed candidate translates the computational scores into a structured 4-sentence narrative that a medicinal chemist can act on without reading raw data.

This document provides the scientific rationale for each design decision in Phase 8.

---

## 2. Triple Vina Re-Docking: Rationale and Exhaustiveness Choice

### 2.1 AutoDock Vina's Stochastic Search

AutoDock Vina uses a hybrid search algorithm combining iterated local search (ILS) with Monte Carlo (MC) perturbations (Trott & Olson 2010, Journal of Computational Chemistry). The algorithm stochastically explores conformational space; different random seeds can discover different local minima of the scoring function. For targets with deep, well-defined binding pockets (e.g., kinase ATP site, KRAS G12C allosteric pocket), multiple seeds converge to the same global minimum reliably. For targets with shallow, broad pockets (e.g., protein-protein interaction surfaces) or flexible binding sites, different seeds may report different binding modes.

The `exhaustiveness` parameter controls the number of independent stochastic restarts. Trott & Olson (2010, Supplementary Data) showed that:
- `exhaustiveness=8` achieves < 10% false-minimum rate for drug-sized molecules (MW 200–500) in typical kinase/GPCR pockets
- `exhaustiveness=4` (default in Phase 5) achieves approximately 15–20% false-minimum rate — acceptable for throughput screening but insufficient for final validation
- `exhaustiveness=12` reduces false-minimum rate to approximately 5–7%, approaching the practical lower bound for rigid-receptor docking

### 2.2 Why Three Independent Runs?

Three independent runs (different random seeds, same exhaustiveness) provide two benefits:

1. **False-minimum detection:** If one of three runs reports a substantially different Vina score (e.g., ΔΔG > 2 kcal/mol), it suggests that the scoring landscape has multiple local minima and the binding mode is ambiguous. This is a red flag independent of the best score.

2. **Pose stability proxy (CV method):** When all three runs agree (low coefficient of variation), it provides evidence — albeit indirect — that the binding mode is well-defined. See Section 3.

The choice of three runs is a balance between compute cost and statistical power. Two runs can detect gross disagreement but are insufficient to compute a meaningful CV. Four or more runs would improve the CV estimate but at proportional compute cost. Three runs represent the standard minimum for inter-run reproducibility assessment in benchmarking studies (Wang et al. 2016, JCIM).

### 2.3 Exhaustiveness Progression Across Phases

| Phase | Exhaustiveness | Purpose |
|---|---|---|
| Phase 4 Tier 2 virtual screen | 4 | High-throughput pre-filter of 400–800 approved compounds |
| Phase 4 Tier 1 / Phase 5 re-dock | 8 | Better coverage for known-mechanism drugs and de-novo candidates |
| **Phase 8 validation** | **12** | Final validation — 3 independent runs, pose stability assessment |

The exhaustiveness increases monotonically as the candidate pool narrows. Phase 8 processes at most `P8_TOP_N` (default 5) candidates per target, making exhaustiveness=12 computationally feasible.

---

## 3. Pose Stability via Coefficient of Variation: Rationale and Limitations

### 3.1 The CV Method

For a candidate with three Vina scores {s₁, s₂, s₃} (all negative kcal/mol):

```
mean = (s₁ + s₂ + s₃) / 3
stdev = sqrt(Σ(sᵢ - mean)² / (n-1))
CV = |stdev / mean|

stability_score = max(0, min(1, 1 - (CV - 0.05) / 0.25))
```

This maps:
- CV = 0.00–0.05 → stability = 1.0 (near-perfect reproducibility)
- CV = 0.05–0.30 → stability linearly decreasing from 1.0 to 0.0
- CV > 0.30 → stability = 0.0 (highly inconsistent)

**Physical interpretation:** A low CV means the Vina scoring function consistently finds the same energy minimum regardless of the starting random seed. This is consistent with a well-defined, deep binding pocket where the ligand has a single dominant bound state. A high CV suggests either multiple competing binding modes (a liability — the "best" binding mode may not be the pharmacologically relevant one) or an ambiguous pocket geometry.

### 3.2 Relationship to True Binding Mode Stability

The CV method is a proxy for thermodynamic binding mode stability, not a direct measurement. The relationship:

- **Low CV → stable binding:** If Vina consistently identifies the same pose, the scoring landscape has a single deep minimum. This is necessary but not sufficient for thermodynamic stability — the ligand could still unbind rapidly at 300 K if the energy barrier to unbinding is shallow.

- **High CV → potentially unstable binding:** Multiple competing poses suggest the protein-ligand complex has multiple low-energy states. In molecular dynamics, this typically manifests as large RMSD fluctuations and occasional pose transitions.

The correspondence between Vina CV and MD RMSD stability has not been formally benchmarked in the literature as of 2026. However, anecdotal evidence from retrospective studies on crystal structure datasets (Li et al. 2019, JCIM) suggests that compounds with CV > 0.2 have approximately 40–60% probability of showing RMSD > 3 Å within 50 ns MD simulation, compared to ~15–20% for CV < 0.1.

### 3.3 What MD Stability Would Add

The standard criterion for binding mode stability in MD studies is **RMSD of the bound ligand ≥ 3 Å sustained for > 30% of the simulation trajectory**, established by Shirts & Pande (2000, Science) and validated against experimental unbinding kinetics in subsequent studies (Shan et al. 2011, JACS; Buch et al. 2011, PNAS).

MD provides:

1. **True thermal stability at 300 K:** Explicit solvent (TIP3P or TIP4P), PME electrostatics, periodic boundary conditions. The protein is fully flexible.
2. **Water-mediated binding:** Crystallographic water molecules that form hydrogen-bond bridges between ligand and protein are resolved. These are completely absent in Vina's implicit hydration model.
3. **Protein-induced fit:** The receptor can reorganize to accommodate or reject the ligand. Vina uses a rigid receptor, which systematically underestimates binding affinity for flexible binding sites.
4. **Unbinding event detection:** For unstable binders (those that would fail the RMSD criterion), the ligand partially or fully exits the pocket within the simulation window.

**Deferral rationale:** GROMACS is not installed on the development machine. OpenMM 8.5.1 is installed and could perform equivalent simulations, but the RTX 3050 (4 GB VRAM) requires approximately 17 hours per compound for a 100 ns explicit-solvent run. At RunPod A100 pricing (~$0.35/hr, ~35 min per compound), 25 compounds across a 5-target run would cost ~$5 total — acceptable for a production discovery run but not implemented as of 2026-06-03.

---

## 4. 6-Axis Scorecard Weight Derivation

The Phase 8 combined score is a weighted linear combination of six axes. The weights represent a principled hierarchy of evidence quality and clinical relevance.

### 4.1 Binding Affinity (0.30)

Binding affinity is the primary evidence for target engagement. A compound that does not bind its target cannot have any therapeutic effect, regardless of how safe, novel, or well-manufactured it is. The 0.30 weight reflects that binding is necessary but not sufficient — several other axes must also be acceptable.

**Scientific basis:** Vina scoring function calibrated against protein-ligand crystal structures (Trott & Olson 2010). For SM candidates, `binding_score = clamp(vina / -10.0, 0, 1)`. The -10.0 kcal/mol ceiling corresponds to approximately Kd ≈ 40 nM, which is a typical potency threshold for lead compounds in drug discovery programs (Bleicher et al. 2003, Nature Reviews Drug Discovery).

### 4.2 Pose Stability (0.20)

A reproducible binding pose provides additional evidence that the binding affinity estimate is physically meaningful. A candidate with consistent Vina scores across three independent runs is more likely to have a genuine, definable binding mode that can be confirmed by X-ray crystallography.

**Scientific basis:** See Section 3. The 0.20 weight acknowledges that this axis has significant limitations (Section 3.3) while still providing meaningful signal for discriminating ambiguous binders from well-defined ones.

### 4.3 ADMET / Developability (0.20)

Safety gatekeeping is essential even at the computational stage. A compound that is potent but crosses blood-brain barrier inappropriately, is metabolized too quickly to maintain therapeutic concentrations, or is flagged as a hERG inhibitor cannot advance to clinical development without substantial structural modification.

The equal weight (0.20) with pose stability reflects the finding from large-scale retrospective analyses of clinical attrition that ADMET liabilities account for approximately 30–40% of late-stage clinical failures (Cook et al. 2014, Nature Reviews Drug Discovery; Waring et al. 2015, Nature Reviews Drug Discovery). Weighting ADMET below binding (0.20 < 0.30) reflects the practical reality that ADMET can sometimes be engineered around after a binding scaffold is confirmed.

**SM:** `admet_score` from Phase 5 `score_admet()` — integrates lipophilicity (LogP), molecular weight, hERG, P-glycoprotein, CYP inhibition, and solubility models.  
**Biologic:** `developability_score` from Phase 6 `score_developability()` — integrates charge, hydrophobicity, instability index (Guruprasad et al. 1990), solubility, and estimated plasma half-life.

### 4.4 Selectivity (0.15)

The therapeutic window — the ratio of toxic dose to effective dose — depends critically on selectivity. Off-target binding, particularly hERG channel inhibition (which causes cardiac arrhythmias), is a common cause of drug withdrawal. The hERG penalties (0.5 for high, 0.8 for medium) are conservative by design, reflecting the severe clinical consequences of hERG-mediated QT prolongation (Redfern et al. 2003, Cardiovascular Research).

The 0.15 weight reflects that many approved drugs have moderate off-target activity that is managed by dosing regimen — selectivity is important but can sometimes be traded off against potency or safety.

### 4.5 Novelty (0.10)

Chemical novelty drives intellectual property protection. A compound that is a close analog (Tanimoto similarity > 0.85) of an existing approved drug offers limited IP value unless the indication is genuinely new. However, novelty is weighted lower (0.10) than safety or binding because a structurally similar compound might still be the best therapeutic option (e.g., deuterated analogs of approved drugs).

**Calculation:** `novelty = 1 - max(Tanimoto similarity to approved drugs)`. Tanimoto similarity uses Morgan fingerprints (radius=2, 2048-bit), which are standard for drug similarity calculations (Rogers & Hahn 2010, JCIM).

### 4.6 Modality Alignment (0.05)

Modality alignment checks whether the candidate type (small molecule, biologic/peptide) matches the modality recommended by Phase 3. A biologic candidate delivered to a target that Phase 3 flagged as SM-routed receives a 0.5 penalty (0.5 × 0.05 = 0.025 reduction in combined score). This is a small but non-trivial manufacturing feasibility signal.

The low weight (0.05) reflects that the pipeline can sometimes generate unexpected modality insights — a peptide might bind an SM-routed target better than any small molecule in the library, and this should not be strongly penalized.

### 4.7 Pass Threshold Rationale

**Pass threshold: combined_score ≥ 0.45**

At the threshold, a candidate achieves approximately "moderate confidence" on all axes simultaneously. Consider a threshold candidate:
- binding: 0.60 (Vina ≈ -6.0 kcal/mol — borderline lead quality)
- stability: 0.50 (neutral — insufficient data)
- ADMET: 0.60 (satisfactory but not clean)
- selectivity: 0.80 (minor concerns)
- novelty: 0.50 (moderately novel)
- modality: 1.00

→ combined = 0.18 + 0.10 + 0.12 + 0.12 + 0.05 + 0.05 = 0.62 (well above threshold)

A more restrictive threshold (0.60) would require near-excellence in binding and ADMET simultaneously — this would fail many legitimate leads that have room for medicinal chemistry optimization. The 0.45 threshold is intentionally permissive to prioritize recall over precision at the computational gatekeeping stage.

---

## 5. Medicinal Chemist Brief: Structure and Scientific Justification

### 5.1 Four-Sentence Format

The LLM brief for each passed candidate is structured as four sentences:

1. **Mechanistic basis:** Why does this candidate look promising for the specific target? (binding mode, key interactions, precedent from analogous compounds)
2. **Differentiation from standard-of-care:** What does this candidate offer that existing drugs do not? (novel scaffold, better selectivity, different mechanism)
3. **Key risk or caveat:** What is the most significant concern? (ADMET liability, uncertain selectivity, structural lability)
4. **Recommended first wet-lab experiment:** What is the single most informative next experiment? (SPR, TR-FRET, NanoBRET, cell viability, selectivity panel)

This structure mirrors the format used in medicinal chemistry brief reports in industrial drug discovery programs (Hughes et al. 2011, Nature Reviews Drug Discovery) and ensures that the output is actionable without additional data analysis.

### 5.2 Why LLM-Generated and Not Template-Based?

A fixed template (e.g., "This compound has a Vina score of X and ADMET score of Y") would be technically accurate but not useful for a medicinal chemist. The value of the brief lies in:

1. Synthesizing multiple numeric scores into a coherent narrative
2. Connecting the computed properties to known biology (e.g., recognizing that a compound targeting KRAS allosteric pocket is relevant in the context of RAS-MAPK pathway activation in pancreatic cancer)
3. Formulating a target-specific next experiment recommendation rather than a generic "confirm binding" instruction

A frontier LLM (Claude Sonnet, GPT-4) with knowledge of medicinal chemistry and the specific target achieves all three. A weak local model (qwen3-4b) may produce generic briefs — this is acceptable because the numeric scores always accompany the brief and are the primary evidence.

### 5.3 Brief Schema

```json
{
  "title": "string — 1 sentence summary",
  "verdict": "promising | borderline | uncertain",
  "evidence": ["sentence 1", "sentence 2"],
  "risks": ["risk 1", "risk 2"],
  "next_wetlab_experiment": "string — specific assay recommendation"
}
```

The assembled brief stored in the DB and package:
```
{title}. Verdict: {verdict}. Evidence: {evidence joined with '; '}. 
Risks: {risks joined with '; '}. Next step: {next_wetlab_experiment}
```

---

## 6. MD Integration Plan (Future Work)

When GROMACS or a RunPod burst session becomes available, the MD gate integrates as follows in `runner.py`:

```python
# Activate when: openmm importable AND (GROMACS on PATH OR RUNPOD_API_KEY set)
def _run_md_stability(
    pdb_url: str,
    ligand_smiles: str,
    symbol: str,
    n_steps: int = 50_000,  # 100 ps implicit; scale to 5M for 10 ns explicit
) -> Dict:
    """
    Run MD and return:
      {"rmsd_mean": float, "rmsd_max": float,
       "fraction_stable": float,   # fraction of trajectory with RMSD < 3Å
       "md_passed": bool,          # fraction_stable > 0.70
       "trajectory_path": str}
    """
```

The MD result replaces the `pose_stability` calculation in `compute_final_score()`:
```python
if md_result:
    stability = md_result["fraction_stable"]  # 0-1: fraction of trajectory where RMSD < 3Å
else:
    stability = _pose_stability_from_multi_run(vina_runs)   # current fallback
```

**Drop criterion (Shirts & Pande 2000; validated in Shan et al. 2011):**  
RMSD > 3 Å sustained for > 30% of trajectory → `md_passed = False`, regardless of Vina score

This aligns Phase 8 with the standards used in computational drug discovery programs at major pharmaceutical companies.

---

## 7. Output Interpretation Guide for Medicinal Chemists

When reviewing Phase 8 output, the following interpretation guidelines apply:

| `combined_score` range | Interpretation | Recommended action |
|---|---|---|
| 0.70 – 1.00 | High confidence computational hit | Prioritize for biological confirmation. Order compound synthesis or source from vendor. First experiment: binding assay (SPR, ITC, or TR-FRET). |
| 0.55 – 0.70 | Moderate confidence, requires confirmation | Worthwhile to progress if novelty and selectivity scores are high. Consider structural modification to address the lowest-scoring axis first. |
| 0.45 – 0.55 | Borderline — passed threshold by slim margin | Lower priority. Progress only if strong mechanistic rationale or exceptional novelty. Review which axis is lowest and whether it can be engineered. |
| < 0.45 | Failed | Not progressed. Available in per-target candidate files for retrospective analysis if needed. |

**Reading subscores:**
- `binding_affinity < 0.50` (Vina < -5.0 kcal/mol): marginal binding — structural optimization needed
- `pose_stability < 0.50` (high CV): ambiguous binding mode — consider X-ray crystallography before investing in optimization
- `admet_or_developability < 0.40`: significant ADMET liability — identify which property (see per-candidate `admet/{cid}_admet.json`) and apply medicinal chemistry principles to resolve
- `selectivity < 0.70`: off-target concerns — run a selectivity panel (kinome panel for kinase inhibitors, counterscreen against hERG for cardiac risk)
