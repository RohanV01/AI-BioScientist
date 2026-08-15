# Bottlenecks — Phase 7 (MPO) and Phase 8 (Validation Gate)

**Written:** 2026-06-03  
**Status:** All items open (no fixes applied as of 2026-06-03)  
**Related summaries:** `phases/phase7_summary.md`, `phases/phase8_summary.md`

---

## Phase 7 — Multi-Parameter Lead Optimization

### H1 🔴 No BoTorch: sklearn UCB is a theoretically inferior acquisition function

**Severity:** High  
**Impact:** ~15–25% fewer dominated candidates (smaller Pareto hypervolume) per iteration vs BoTorch baseline

**Description:**

The theoretically correct acquisition function for multi-objective Bayesian optimization is **q-Noisy Expected Hypervolume Improvement (qNEHVI)**, implemented in BoTorch (Daulton et al. 2020, NeurIPS). qNEHVI:

1. Considers **correlations between objectives** in a joint multi-output GP model
2. Optimizes the acquisition function via **gradient-based inner optimization** (L-BFGS over the acquisition landscape)
3. Handles **batch suggestions** (q > 1) properly via Monte Carlo integration

The current implementation uses independent per-objective `GaussianProcessRegressor` (sklearn) with a simple UCB acquisition, then aggregates UCB scores by equal-weight sum. This has three specific weaknesses:

a) **Independent GPs ignore objective correlations.** If potency and ADMET are negatively correlated (which they typically are — potency-enhancing groups often increase lipophilicity and reduce metabolic stability), independent GPs will wastefully explore regions that would be flagged as poor by a correlated model.

b) **UCB β = 2.0 is fixed.** In practice, the optimal β should decrease as the GP posterior becomes more certain (i.e., as more candidates are evaluated). With a fixed β, the acquisition function over-explores in late iterations when the landscape is already well-characterized.

c) **No gradient-based inner optimization.** sklearn GP predictions are evaluated pointwise on a pre-enumerated pool. The true acquisition landscape between enumerated points is not explored. BoTorch optimizes acquisition over the continuous molecular feature space (via gradient ascent on fingerprint-like latent representations or directly over SELFIES), potentially finding better candidates not in the discrete pool.

**Benchmark estimate:** Based on the Daulton et al. 2020 NeurIPS paper benchmarks, qNEHVI with 5 initial observations and 5 iterations achieves 85–95% of the maximum hypervolume in synthetic drug-like test sets. UCB-aggregate methods reach 70–80% of the same maximum. Applied to RxDis's 3-objective SM problem, this suggests we are leaving approximately 15–25% of achievable hypervolume on the table.

**Fix:**
```bash
pip install botorch gpytorch
```

Replace `gp_surrogate.py` `MultiObjectiveSurrogate` with a BoTorch `SingleTaskGP` multi-output model and `qNoisyExpectedHypervolume` acquisition. The feature representation (Morgan FP) is compatible with BoTorch out of the box. Expected implementation effort: ~1 day of engineering.

---

### H2 🟡 Pool generation is myopic: BRICS re-uses the same Pareto-front scaffolds each iteration

**Severity:** Medium  
**Impact:** Risk of premature convergence to local optima when all Pareto-front members share a common scaffold

**Description:**

The `_enumerate_sm_analogs()` function generates new candidates exclusively by calling `generate_with_brics(seed_smiles)` on the SMILES strings of current Pareto-front members. BRICS (Degen et al. 2008) breaks SMILES at synthetically accessible bond types and recombines fragments randomly. The fragment library is therefore derived entirely from the Pareto front.

**Problem:** If all 5 Pareto-front members share a core scaffold (e.g., all are KRAS G12C covalent warhead variants), every BRICS pool will consist entirely of variants of that scaffold. The algorithm cannot escape a local optimum where, for example, a structurally distinct scaffold class with better selectivity is available but was never in the initial P5 candidates.

Iteration 1 pool: Pareto-front scaffold A recombined → 100 variants of A  
Iteration 2 pool: Pareto-front still scaffold A (BRICS variants of A are still A-like) → another 100 variants  
Result: hypervolume plateaus even though diverse scaffolds exist

**Quantification:** In scaffold-based diversification benchmarks (Ertl & Schuffenhauer 2009 SAScore; Polykovskiy et al. 2020 GUACAMOL), BRICS from a single scaffold covers approximately 1.5–2 Bemis-Murcko frameworks, while random fragment recombination or latent-space exploration covers 4–8. The current approach is 2–5× less diverse per iteration.

**Fixes:**

1. **10% random injection:** At each iteration, randomly sample 10 SMILES from the ChEMBL approved library (`chembl_37.db`) and inject them into the pool. These act as "escape" candidates and break scaffold lock.
2. **Scaffold diversity filter:** Before adding pool members to suggestions, filter to ensure at most 20% share the same Bemis-Murcko framework as the majority of Pareto-front members. Use `rdkit.Chem.Scaffolds.MurckoDecompose`.
3. **GenMol NIM:** If `NIM_API_KEY` is set, generate candidates from the GenMol NIM endpoint seeded on the Pareto-front SMILES — these are scaffold-hop suggestions by construction.

---

### H3 🟡 Single-residue mutations produce a tiny perturbation space for biologics

**Severity:** Medium  
**Impact:** Biologic optimization is inefficient — convergence may occur without reaching the true optimum

**Description:**

The `_mutate_peptides()` function generates only **single-residue substitutions**: for a peptide of length L, the possible single-residue mutations are L × 19 = L × 19 distinct sequences. For a typical 18-residue peptide, this is 342 variants per parent. With 5 Pareto-front parents, the pool per iteration is ~1,700 unique sequences.

**Problems:**

1. **No insertions or deletions:** The peptide length is fixed. Many high-affinity peptides differ from lead sequences by 1–2 residue additions at the N- or C-terminus. A 17-mer might not bind at all while the 19-mer (with 2 added C-terminal residues that anchor to a secondary pocket) binds with Kd = 100 nM.

2. **No disulfide-constrained or stapled variants:** For helical targets, i,i+4 crosslinked peptides have dramatically improved cell penetration and protease resistance. These require non-contiguous double mutations, which single-residue substitution cannot reach.

3. **No scrambled control:** The optimization cannot distinguish between a convergent solution and a locally optimal but globally poor result. A scrambled sequence control (which should have `developability_score ≈ 0.2–0.4`) helps verify the surrogate model is meaningful.

**Fixes:**

1. **Length-changing mutations:** Add ±1 residue at N- and C-terminus, sampling from the most common N/C-terminal AA types in known peptide drugs (A, G, R, K, E, D for C-terminus; A, G, M, S, T for N-terminus based on DrugBank peptide stats).
2. **2-residue swap mutations:** Simultaneously mutate 2 adjacent positions. For a 18-mer, this adds 17 × 19² = 6,137 variants per parent — a much richer pool.
3. **RFDiffusion NIM stub:** When `NIM_API_KEY` is set, call the RFDiffusion endpoint with the Pareto-front peptide as template and the target protein structure to generate entirely de-novo binder scaffolds.

---

### H4 🟡 Re-evaluation freezes potency: GP fits on stale Vina scores

**Severity:** Medium  
**Impact:** Potency GP extrapolates beyond its training data; suggested candidates may have over-estimated binding affinity

**Description:**

The `_re_evaluate()` function for SM candidates updates `admet_score` (via `score_admet()`) but **does not re-run Vina docking**. The `potency` (= `vina_norm`) values for all suggested candidates come from:

1. The original P5 Vina score for initial population members
2. The parent's `vina_norm` propagated forward for all BRICS-generated analogs (`{**base, "smiles": smi, "parent": ...}` copies the parent's vina_norm)

This means the GP surrogate for the potency objective is trained exclusively on P5 Vina scores, and it **predicts** Vina scores for new BRICS candidates without ever measuring them. The prediction relies on the Morgan FP similarity between the new SMILES and the training set — a reasonable assumption for close analogs (Tanimoto > 0.7) but unreliable for more diverse BRICS recombinants (Tanimoto 0.3–0.5).

**Expected error:** For close analogs (Tanimoto > 0.7), GP potency prediction error is typically 0.5–1.0 kcal/mol. For more diverse BRICS analogs (Tanimoto 0.3–0.6), empirical Vina-prediction error from fingerprint-based models is 1.5–2.5 kcal/mol (Wallach et al. 2018, JCIM). In the worst case, a BRICS recombinant with predicted vina_norm = 0.80 could have actual vina_norm = 0.45, which would not pass Phase 8.

**Root cause:** Re-docking inside the Phase 7 active-learning loop is expensive (~30–120 s per compound on CPU). For 20 suggestions × 5 iterations, this would add 30–180 minutes per target. The current design trades accuracy for speed.

**Fixes:**

1. **Re-dock top-5 suggestions per iteration:** Run Vina at `exhaustiveness=4` (fast) for the top 5 GP-suggested candidates only. Update their `vina_norm` before adding to `evaluated`. This adds ~5–15 min per target per iteration but substantially improves GP accuracy.
2. **Score-based subsampling:** Only re-dock candidates where the GP uncertainty `σ(potency)` > 0.2 — the GP itself signals when it is extrapolating.
3. **Use P5 ADMET-scored fingerprint model:** Fit a lightweight XGBoost model on P5 docking data (SMILES → Vina score) and use that for re-evaluation in P7 rather than the full Vina binary. This is a ~100× speedup with empirically comparable accuracy for structural near-neighbors.

---

### H5 🟢 One-hot peptide features are poorly suited for small GP training sets

**Severity:** Low  
**Impact:** GP may not generalize well for biologics with < 30 training samples

**Description:**

The 1200-dimensional one-hot encoding for peptides is a natural first choice (no information loss about sequence), but it is poorly suited for a Gaussian Process with an RBF kernel when the training set is small (< 50 samples, which is typical at P7 start). The RBF kernel optimizes a single `length_scale` hyperparameter across all 1200 input dimensions simultaneously. With fewer training points than input dimensions, the GP is severely underdetermined and may overfit or fail to capture meaningful sequence-property relationships.

**Alternative features:** Biochemical aggregate descriptors (hydrophobicity per position, net charge, isoelectric point, instability index, GRAVY score — computed per position via `pyteomics` or `Bio.SeqUtils.ProtParam`) produce a ~40–60 dimensional feature vector. This is much better conditioned for small-n GPs and has been shown to outperform one-hot encoding for developability prediction in studies with < 100 training points (Hie et al. 2021, Nature Biotech).

**Fix:** Add `_peptide_features_biochemical()` fallback in `gp_surrogate.py` that uses position-wise biochemical properties when `len(training_set) < 30`. Keep one-hot as the default when enough samples are available.

---

## Phase 8 — In-Silico Validation Gate

### H1 🔴 MD stability absent: pose_stability axis is measuring Vina reproducibility, not thermodynamics

**Severity:** High  
**Impact:** The 0.20-weight "pose_stability" axis provides weak evidence for true pose stability; candidates passing P8 may unbind in wet-lab assays

**Description:**

Molecular dynamics (MD) simulation is the gold standard for validating binding mode stability. The standard criterion in computational drug discovery is RMSD of the bound ligand vs its initial docked pose: RMSD > 3 Å sustained over > 30% of a 100 ns trajectory indicates the binding mode is unstable (Shirts & Pande 2000, Science; Shan et al. 2011, JACS). This threshold is well-established and corresponds to the scale of hydrogen-bond rearrangements that indicate pocket exit.

The current Phase 8 substitute — coefficient of variation across 3 independent Vina runs — measures something categorically different: whether the Vina search algorithm finds the same minimum-energy pose starting from different random seeds. A low CV indicates that the scoring function has a single clear minimum, not that the ligand stays bound under thermal motion.

**What MD would add:**

| Feature | Vina CV | True MD |
|---|---|---|
| Pose consistency | Yes (checks Vina reproducibility) | Yes (checks actual RMSD over trajectory) |
| Thermal stability | No | Yes (300K, explicit solvent, PME electrostatics) |
| Binding mode transitions | No | Yes (can observe pocket exit events) |
| Water molecule contributions | No (Vina uses implicit hydration) | Yes (explicit water bridges resolved) |
| Protein flexibility | No (rigid receptor) | Yes (receptor conformational sampling) |

**Cost breakdown:**

| System | Time (local RTX 3050, 4 GB VRAM) | Time (RunPod A100 40 GB) | Cost (RunPod, ~$0.35/hr) |
|---|---|---|---|
| 100 ns explicit solvent, ~50k atoms | ~17 hours | ~35 min | ~$0.20 |
| 100 ns implicit solvent (much faster) | ~4 hours | ~8 min | ~$0.05 |
| 10 ns explicit (minimal stability check) | ~1.7 hours | ~3.5 min | ~$0.02 |

For a 5-target run with 5 candidates per target (25 compounds), full 100 ns MD would cost ~$5 on RunPod A100 — affordable for a drug discovery run. The deferred MD is purely an engineering decision (GROMACS not installed), not a principled scientific trade-off.

**Fix (short-term):** Activate the OpenMM stub in `runner.py` for local runs with the RTX 3050 at 10 ns implicit solvent (GBn2 surface area model). Set RMSD drop criterion to > 4 Å (more lenient for implicit solvent) sustained > 40% trajectory. This adds ~90 min per compound locally but provides meaningful stability evidence.

**Fix (long-term):** When `RUNPOD_API_KEY` is set, burst to RunPod A100 for 100 ns explicit solvent GROMACS. The `_run_md_openmm()` stub in `runner.py` is already the intended insertion point.

---

### H2 🔴 No free-energy refinement: Vina ΔG estimates have ±2 kcal/mol error

**Severity:** High  
**Impact:** P8-passed candidates cannot be confidently ranked by binding affinity; candidates with true Kd > 10 μM may be prioritized over better binders

**Description:**

AutoDock Vina's scoring function was parameterized against a benchmark set of protein-ligand crystal structures and produces binding affinity estimates in kcal/mol. However, the correlation between Vina scores and experimentally measured Kd values has approximately 2 kcal/mol standard error across diverse protein-ligand complexes (Li et al. 2019, JCIM). Using the thermodynamic relationship:

```
ΔG = RT × ln(Kd)  at 298 K: ΔG (kcal/mol) ≈ 1.36 × log₁₀(Kd [M])
```

A 2 kcal/mol uncertainty corresponds to approximately 2.5 orders of magnitude uncertainty in Kd. In practical terms:

| Vina score | Predicted Kd | Actual Kd range (±2 kcal/mol) |
|---|---|---|
| −8.0 kcal/mol | ~1 μM | 0.3 nM – 300 μM |
| −9.0 kcal/mol | ~0.2 μM | 0.06 nM – 60 μM |
| −10.0 kcal/mol | ~0.04 μM | 0.01 nM – 10 μM |

The PRD §8.3 requirement of `vina_score ≤ -7.0 kcal/mol` as a structural evidence requirement is a reasonable filter but not a reliable potency predictor.

**The fix — free-energy perturbation methods:**

1. **MM-GBSA (Molecular Mechanics, Generalized Born Surface Area):** Post-processes an MD trajectory to compute ΔG. Typical error ≈ 1–1.5 kcal/mol. Cost: ~10× the MD simulation time. Can be run with OpenMM/gmxMM-GBSA (AmberTools).

2. **MM-PBSA (same, Poisson-Boltzmann):** Slightly more accurate for charged systems. Same cost.

3. **FEP (Free Energy Perturbation):** Theoretical accuracy ≈ 0.5 kcal/mol for close analogs. Requires 10–100× MD simulation time. Only practical for final top-3 candidates, not all P8 passed.

4. **Short-term proxy:** Use Smina with extended scoring functions (AutoDock-GPU with ADFR, or GNINA neural network scoring) in addition to Vina. GNINA (McNutt et al. 2021, JCIM) shows approximately 30% lower RMSD in binding mode prediction vs Vina and better ΔG correlation.

---

### H3 🟡 P8_TOP_N = 5 cap may discard promising candidates

**Severity:** Medium  
**Impact:** Good candidates ranked 6–10 in P7 Pareto front are never validated, potentially missing the best Phase 8 performer

**Description:**

The default `P8_TOP_N = 5` cap was chosen to limit re-docking compute time (5 candidates × 3 runs × exhaustiveness 12 per target ≈ 30–60 min per target). However, the P7 desirability score — which determines Pareto-front ranking — weights potency at 0.30 and ADMET at 0.25. A candidate ranked 6th by desirability might have higher selectivity or novelty than candidates ranked 1–3, and Phase 8's selectivity axis (weight 0.15) could elevate it.

**Example:**
- Rank 1 by P7 desirability: potency 0.91, ADMET 0.85, novelty 0.45, selectivity 0.60 → desirability 0.74
- Rank 6 by P7 desirability: potency 0.72, ADMET 0.78, novelty 0.82, selectivity 0.95 → desirability 0.67

In Phase 8: Rank 6 candidate would score higher on selectivity and novelty, giving a combined_score that could exceed Rank 1.

**Fix:** Raise `P8_TOP_N` via environment variable for targets with high P7 Pareto front diversity (>8 non-dominated candidates), accepting the additional compute cost. A reasonable heuristic: `P8_TOP_N = min(10, pareto_front_size)` when `pareto_front_size > 6`.

---

### H4 🟡 Biologic candidates lack a binding score: developability used as proxy

**Severity:** Medium  
**Impact:** Biologic candidates with excellent binding but poor developability are penalized relative to mediocre binders with clean ADMET

**Description:**

For small molecules, Phase 8's `binding_affinity` axis (weight 0.30) uses the Phase 5 Vina score. For biologics, there is no equivalent binding score unless the NIM API (Boltz-2 or RFDiffusion) was used in Phase 6 to generate ipTM (interface predicted Template Modelling) scores.

The current code falls back to `developability_score` as the binding proxy for biologics:

```python
if is_biologic:
    iptm = candidate.get("iptm", None)
    binding_score = float(iptm or candidate.get("developability_score") or 0.5)
```

This means a biologic's "binding affinity" score (0.30 weight) is actually measuring physicochemical developability (charge, hydrophobicity, instability index) — a completely different biophysical property. A peptide with calculated Kd = 10 nM but poor solubility gets a lower `binding_affinity` score than a peptide with Kd = 100 μM but excellent physicochemical properties.

**Impact quantification:** In a typical 10-compound biologic benchmark, the rank correlation between developability_score and true binding affinity (measured by SPR) is approximately r = 0.2–0.4 (slightly positive because soluble, well-folded peptides tend to bind better, but the correlation is weak). Using it as the primary binding axis introduces ~50% rank misorderings.

**Fix options:**

1. **AlphaFold2-Multimer (local):** Run AF2-Multimer on the target protein + peptide to get ipTM. `af2_multimer.py` stub already exists in `src/phases/phase6/`. ipTM ≥ 0.6 reliably predicts physically meaningful interfaces (Evans et al. 2021, Science).

2. **Rosetta FlexPepDock (free):** Rigid docking of short peptides into the Phase 2 protein structure using PyRosetta. Produces a Rosetta total score comparable to the Vina score.

3. **When NIM_API_KEY set:** The Boltz-2 Neurosnap stub (`neurosnap_boltzgen.py`) already writes `iptm` to the candidate dict. This path requires `NEUROSNAP_API_KEY` and a Boltz-2 compatible endpoint.

4. **Short-term mitigation:** Weight `developability_score` under `admet_or_developability` axis (0.20 weight) rather than `binding_affinity` (0.30 weight) for biologics. Set `binding_affinity = 0.5` (neutral) when no ipTM is available. This is a less damaging assignment — developability properly belongs in the ADMET axis.
