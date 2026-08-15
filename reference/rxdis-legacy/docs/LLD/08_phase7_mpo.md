# LLD-08: Phase 7 — Multi-Parameter Optimization (MPO)

**Source:** `src/phases/phase7/`  
**PRD:** `docs/PRD_phase7_mpo.md`  
**Scientific Protocol:** `Scientific Protocol/phase7_mpo.md`  
**Celery queue:** `cpu` (sklearn GP, Pareto), `hosted` (re-evaluation via P5/P6 steps)  
**Input:** Phase 5 `de_novo_sm` + Phase 6 `biologic` + Phase 2/3 context + `RunConfig`  
**Output:** `phase7_output: dict` → `phase_results.output_json` (phase=7) + updated `candidates` rows

---

## 1. Module Structure

```
src/phases/phase7/
├── runner.py        — per-target optimization loop, writes DB
├── pareto.py        — Pareto front computation, hypervolume (WFG sweep)
└── gp_surrogate.py  — sklearn GP per objective, UCB acquisition, Morgan FP features
```

---

## 2. Entry Point

```python
def run_phase7(
    run_id: str,
    config: RunConfig,
    db,
    phase5_output: Optional[dict],
    phase6_output: Optional[dict],
    phase2_output: dict,
    phase3_output: dict,
) -> dict:
    """
    Collects candidates from P5 and P6 per target.
    For each target: run active-learning MPO loop.
    Returns phase7 output dict.
    """
```

---

## 3. Objectives and Feature Representations

### Objectives (5 for SM, 5 for biologic)

| Objective | SM source | Biologic source | Optimisation direction |
|---|---|---|---|
| `potency` | `vina_score` (kcal/mol) | `iptm` | Maximise |
| `selectivity` | Tanimoto distance from anti-target scaffold | `1 - off_target_iptm` | Maximise |
| `admet` | `admet_norm` from P5 scoring | `dev_score` from P6 developability | Maximise |
| `novelty` | `1 - tanimoto_to_approved` | sequence diversity vs known peptides | Maximise |
| `sa` | `1 - sa_score/10` | (not applicable — dev_score covers) | Maximise |

### Feature representation for GP

```python
def _molecule_to_features(smiles: str) -> np.ndarray:
    """
    Morgan fingerprint: radius=2, nBits=2048, useFeatures=False.
    Returns: numpy array shape (2048,), dtype float32.
    """

def _peptide_to_features(sequence: str) -> np.ndarray:
    """
    Amino acid composition vector (20 dims) +
    dipeptide composition vector (400 dims) +
    sequence length (1 dim) +
    net charge at pH 7.4 (1 dim).
    Returns: numpy array shape (422,), dtype float32.
    """
```

---

## 4. `gp_surrogate.py` — Gaussian Process Surrogate

```python
def fit_gp_per_objective(
    X: np.ndarray,            # (n_candidates, n_features)
    Y: np.ndarray,            # (n_candidates, n_objectives)
    objective_names: List[str],
) -> List[GaussianProcessRegressor]:
    """
    One sklearn GP per objective.
    Kernel: Matern(length_scale=1.0, nu=2.5) * ConstantKernel(1.0)
    Optimizer: L-BFGS-B, n_restarts_optimizer=3
    Normalize y: True
    Returns list of fitted GP models (one per objective).
    """

def ucb_acquisition(
    gp_models: List[GaussianProcessRegressor],
    X_candidates: np.ndarray,   # candidate feature vectors to score
    beta: float = 2.0,          # exploration-exploitation trade-off
) -> np.ndarray:
    """
    For each candidate:
      For each objective GP:
        mu_i, sigma_i = gp.predict(x, return_std=True)
        ucb_i = mu_i + beta * sigma_i
    Aggregate: mean(ucb_i across objectives)
    Returns: array shape (n_candidates,) of acquisition scores.
    """

def suggest_next_batch(
    gp_models: List[GaussianProcessRegressor],
    existing_X: np.ndarray,
    molecule_pool: List[str],    # SMILES or sequences to sample from
    batch_size: int = 20,
    modality: str = "sm",        # "sm" | "biologic"
) -> List[str]:
    """
    Generate candidate pool:
      SM: BRICS fragmentation of existing candidates → ~5000 SMILES
      Biologic: single-residue mutations of existing sequences → ~500 sequences
    
    Convert pool to features.
    Score via UCB acquisition.
    Return top batch_size by UCB score (deduplication vs existing_X via Tanimoto/Hamming).
    """
```

---

## 5. `pareto.py` — Pareto Front and Hypervolume

```python
def compute_pareto_front(
    scores: np.ndarray,    # (n_candidates, n_objectives), all maximise
) -> np.ndarray:
    """
    Pure Python Pareto non-dominance check.
    A solution i dominates j if: all(scores[i] >= scores[j]) AND any(scores[i] > scores[j])
    Returns: boolean mask of non-dominated (Pareto-optimal) solutions.
    O(n^2 * m) complexity — fine for n < 500.
    """

def compute_hypervolume_2d(
    pareto_points: np.ndarray,    # (n_pareto, 2) — 2D sweep (first two objectives)
    reference_point: np.ndarray = np.array([0.0, 0.0]),
) -> float:
    """
    WFG (Walking Fish Group) hypervolume sweep for 2D.
    Sort by first objective descending. Accumulate incremental area.
    Returns: hypervolume indicator (scalar).
    Used as convergence metric across iterations.
    """

def compute_desirability(
    scores: np.ndarray,     # (n_candidates, n_objectives)
    weights: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Derringer-Suich desirability function:
      For each objective: d_i = (score_i - min_i) / (max_i - min_i) clamped [0, 1]
    Overall: D = (prod(d_i^w_i))^(1/sum(w_i))
    Default weights: [0.3, 0.2, 0.2, 0.15, 0.15]  (potency, selectivity, ADMET, novelty, SA)
    Returns: array shape (n_candidates,) of desirability scores.
    """
```

---

## 6. Active-Learning Loop (`runner.py`)

```python
def run_mpo_for_target(
    symbol: str,
    sm_candidates: List[dict],       # from Phase 5
    bio_candidates: List[dict],      # from Phase 6
    config: RunConfig,
    phase2_target: dict,
    phase3_routing: dict,
    db,
    run_id: str,
) -> dict:
    """
    max_iterations = 5
    convergence_threshold_hv = 0.01   # 1% hypervolume improvement
    budget_spent = 0.0

    Initialise:
      all_candidates = sm_candidates + bio_candidates
      X = compute features for all
      Y = extract objective vectors from subscores
    
    Loop (max_iterations):
      1. Fit GP per objective on (X, Y)
      2. Suggest next batch of 20 (BRICS/mutation pool via UCB)
      3. Evaluate batch via P5/P6 re-evaluation functions:
         SM: phase5.admet + phase5.redock_and_rescore (fast path, no generation)
         Biologic: phase6.validate_by_refolding (AF2 NIM or Boltz-2)
      4. Add evaluated batch to (X, Y)
      5. Compute Pareto front + hypervolume
      6. LLM gate 7.2_iteration_review
      7. Check stop conditions:
           - HV improvement < 1% vs previous iteration → STOP
           - iteration count >= max_iterations → STOP
           - budget_spent >= config.budget_hosted_usd → STOP
      8. Log hypervolume to compute_log
    
    Final Pareto front: extract from full (X, Y) after last iteration.
    Update candidates.subscores in DB with optimised objective values.
    """
```

**LLM gate `7.2_iteration_review`:**
```
When: after each iteration
Prompt: "MPO iteration {iter}/{max_iter} for target {symbol}.
         Chemical/sequence space explored: {diversity_summary}.
         Current Pareto front size: {n_pareto}.
         Hypervolume: {hv:.4f} (improvement: {hv_delta:.1%}).
         Budget remaining: ${budget_remaining:.2f}.
         Suggested candidates this iteration: {top3_smiles_or_seqs}.
         Are we exploring/exploiting appropriately?
         Any suggestions that look chemically unreasonable?"
Output schema: {
  "space_explored": "...",
  "balance_assessment": "exploring" | "exploiting" | "balanced",
  "flagged_unreasonable": ["smiles_or_seq1", ...],
  "recommendation": "continue" | "shift_focus" | "stop"
}
Fallback: continue if HV improving; stop if not
```

---

## 7. Output JSON Contract

```json
{
  "optimized": {
    "LRRK2": {
      "pareto_front": [
        {
          "id": "DNSM_047",
          "smiles": "...",
          "desirability": 0.88,
          "objectives": {
            "potency": -9.4,
            "admet": 0.82,
            "sa": 2.7,
            "selectivity": 0.90,
            "novelty": 0.69
          }
        }
      ],
      "iterations_run": 4,
      "hypervolume_final": 0.71,
      "hypervolume_trajectory": [0.51, 0.63, 0.69, 0.71],
      "n_candidates_evaluated": 97
    }
  },
  "n_targets": 8,
  "n_pareto_total": 34,
  "wall_time_s": 5400
}
```

---

## 8. DB Writes

```
phase_results: phase=7, running → completed
candidates: UPDATE subscores with final optimised objective values
            UPDATE combined_score = desirability for Pareto-optimal candidates
decisions: gate="7.2_iteration_review" per iteration per target
compute_log: step="gp_fit" service="local" wall_time_s
             step="ucb_suggest" service="local"
             step="candidate_eval" service="NIM/neurosnap/local"
             step="hypervolume" service="local"
```

---

## 9. Failure / Recovery

| Failure | Recovery |
|---|---|
| No P5 or P6 candidates | Skip MPO; pass existing P4 candidates directly to P8 |
| No HV improvement after 1 iteration | Halt immediately; pass best parents forward |
| GP suggests chemically unreasonable candidates | LLM flag drops them; re-suggest from BRICS pool |
| Budget exhausted mid-loop | Stop cleanly; keep current Pareto front |
| sklearn GP fit failure (singular matrix) | Add nugget regularisation (alpha=1e-6); retry |

---

## 10. Performance Characteristics

| Step | Typical time | Notes |
|---|---|---|
| GP fit (100 candidates, 5 objectives) | < 30 s | sklearn, CPU only |
| UCB suggest (5K pool) | < 10 s | vectorised |
| SM re-evaluation (20 mols, local) | ~3 min | Vina + ADMET |
| Biologic re-evaluation (20 seqs, AF2 NIM) | ~20 min | API-bound |
| Pareto + HV | < 1 s | pure Python |
| **5 iterations (SM target)** | **~20 min** | |
| **5 iterations (biologic target)** | **~2 h** | AF2 NIM latency dominates |
