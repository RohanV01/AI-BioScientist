# LLD-09: Phase 8 — Validation Gate

**Source:** `src/phases/phase8/`  
**PRD:** `docs/PRD_phase8_validation_gate.md`  
**Scientific Protocol:** `Scientific Protocol/phase8_validation_gate.md`  
**Celery queue:** `cpu` (scorecard), `hosted` (triple Vina re-dock, candidate briefs)  
**Input:** Phase 7 optimised candidates + Phase 4 repurposing candidates + Phase 2/3 context  
**Output:** `phase8_output: dict` → `phase_results.output_json` (phase=8) + updated `candidates` rows

---

## 1. Module Structure

```
src/phases/phase8/
├── runner.py      — per-target validation, writes candidates to DB
└── scorecard.py   — 6-axis final score + triple Vina pose stability
```

---

## 2. Key Design Decision: MD Skipped

MD simulation (GROMACS / OpenMM) was opted out by the user. Pose stability is instead confirmed by **triple Vina re-docking** with exhaustiveness=12 and computing the CV (coefficient of variation) of scores across 3 runs as a stability proxy.

---

## 3. Entry Point

```python
def run_phase8(
    run_id: str,
    config: RunConfig,
    db,
    phase7_output: Optional[dict],
    phase4_output: Optional[dict],
    phase2_output: dict,
    phase3_output: dict,
) -> dict:
    """
    Collects top 5-10 candidates per target from P7 (or P4 if P7 skipped).
    For each candidate: run triple-Vina re-dock + final scorecard.
    Returns phase8 output dict.
    """
```

---

## 4. Candidate Selection

```python
def _select_top_candidates(
    phase7_output: Optional[dict],
    phase4_output: Optional[dict],
    symbol: str,
    max_candidates: int = 10,
) -> List[dict]:
    """
    Priority:
    1. Pareto-optimal candidates from P7 (sorted by desirability desc)
    2. P4 repurposing candidates (sorted by repurposing_score desc)
       — only if no P7 candidates for this target
    3. If both: top min(5, n_p7) from P7 + top min(5, n_p4) from P4
    Cap: max_candidates total
    """
```

---

## 5. Triple Vina Re-Docking (`scorecard.py`)

```python
def run_triple_vina(
    smiles: str,
    receptor_pdbqt: str,
    pocket: dict,
    exhaustiveness: int = 12,
) -> Tuple[float, float, bool]:
    """
    Run AutoDock Vina 3 times with different random seeds (42, 137, 2049).
    Each run: exhaustiveness=12 (vs 8/4 in Phase 4 — more thorough).
    
    scores = [run1_best_score, run2_best_score, run3_best_score]
    mean_score = mean(scores)
    cv = std(scores) / abs(mean_score)   # coefficient of variation
    
    pose_stable = cv < 0.1  (< 10% variation = consistent binding mode)
    
    If pose_stable == False:
      drop candidate (log "unstable pose")
    
    Returns: (mean_score, cv, pose_stable)
    
    Note: This replaces MD in the absence of GROMACS / RunPod.
    CV < 0.1 is the stability proxy — consistent pose across 3 independent
    docking runs indicates a well-defined binding mode.
    """
```

---

## 6. Final Scorecard (`scorecard.py`)

```python
def compute_final_scorecard(
    candidate: dict,
    vina_mean: float,
    cv: float,
    target: dict,
    config: RunConfig,
) -> Tuple[float, dict]:
    """
    6-axis scoring (default weights):
    
    binding_affinity_score:
      SM: min(1.0, abs(vina_mean) / 12.0)
      Biologic: candidate["iptm"]   (already in [0, 1])
    
    pose_stability_score:
      SM: 1.0 - cv   (low CV = high stability)
      Biologic: 1.0 - candidate["pae_interface"] / 20.0
    
    admet_score:
      SM: candidate["subscores"]["admet"] normalized
          heuristic: 1.0 - n_flags * 0.2 (max 1 flag tolerated)
      Biologic: candidate["subscores"]["dev_score"]
    
    selectivity_score:
      candidate["subscores"].get("selectivity", 0.5)   # from P7 optimisation
      Default 0.5 if not computed
    
    novelty_score:
      SM: 1.0 - candidate["subscores"]["tanimoto_to_approved"]
      Biologic: 0.7 (assumed novel — no established baseline)
    
    modality_alignment_score:
      1.0 if candidate kind matches phase3 primary modality for this target
      0.7 if matches secondary
      0.3 if neither
    
    Default weights by indication_type:
    
      chronic:
        binding=0.30, stability=0.20, admet=0.25, selectivity=0.15, novelty=0.05, modality=0.05
      oncology:
        binding=0.35, stability=0.20, admet=0.15, selectivity=0.15, novelty=0.10, modality=0.05
      acute:
        binding=0.30, stability=0.20, admet=0.20, selectivity=0.15, novelty=0.10, modality=0.05
    
    combined_score = weighted sum of 6 axes
    
    Returns: (combined_score, subscores_dict)
    """
```

---

## 7. LLM Gates

### Gate `8.3_candidate_brief`

**When:** For every candidate passing combined_score ≥ 0.5.

```
Prompt: "Drug candidate for {symbol} in {disease_label}.
         Candidate: {id}. SMILES or sequence: {identifier}.
         
         Scores: binding={binding_affinity_score:.2f}, stability={stability_score:.2f},
                 ADMET={admet_score:.2f}, selectivity={selectivity_score:.2f},
                 novelty={novelty_score:.2f}
         Vina/ipTM: {primary_affinity}. Pose CV: {cv:.3f}.
         ADMET highlights: {admet_summary}.
         
         Write a concise drug-candidate summary for a medicinal chemist.
         Include: binding assessment, key risks, recommended next wet-lab experiment."
Output schema: {
  "title": "...",
  "verdict": "strong" | "moderate" | "weak",
  "evidence": ["...", "..."],
  "risks": ["...", "..."],
  "next_wetlab_experiment": "..."
}
Fallback: generate templated summary from raw scores
```

---

## 8. Output JSON Contract

```json
{
  "targets": [
    {
      "symbol": "LRRK2",
      "target_validation_score": 0.79,
      "candidates": [
        {
          "id": "DNSM_047",
          "kind": "de_novo_sm",
          "smiles": "...",
          "candidate_score": 0.84,
          "combined_score": 0.81,
          "subscores": {
            "binding_affinity": 0.89,
            "pose_stability": 0.93,
            "admet_or_developability": 0.82,
            "selectivity": 0.88,
            "novelty": 0.69,
            "modality_alignment": 1.0
          },
          "vina_triple": {
            "run1": -10.2, "run2": -9.8, "run3": -10.1,
            "mean": -10.03, "cv": 0.02, "pose_stable": true
          },
          "brief": {
            "title": "DNSM_047: potent LRRK2 inhibitor with clean ADMET",
            "verdict": "strong",
            "evidence": ["Triple-Vina CV 0.02 indicates stable pose", ...],
            "risks": ["Limited selectivity data vs LRRK1"],
            "next_wetlab_experiment": "TR-FRET binding assay at 1-10 µM"
          }
        }
      ]
    }
  ],
  "n_targets": 8,
  "n_candidates_passed": 21,
  "n_candidates_dropped": 11,
  "wall_time_s": 900
}
```

---

## 9. DB Writes

```
phase_results: phase=8, running → completed
candidates: UPDATE combined_score = final combined_score
            UPDATE subscores = {6-axis scores + vina_triple}
            artifact_paths = [best_pose_pdbqt in Storage]
decisions: gate="8.3_candidate_brief" per passing candidate
compute_log: step="triple_vina" service="local_cpu"
             step="scorecard" service="local"
```

---

## 10. Failure / Recovery

| Failure | Recovery |
|---|---|
| Zero candidates pass (combined_score ≥ 0.5) for a target | Abort that target; proceed to next; mark "no_valid_candidates" |
| Zero candidates pass for ALL targets | Mark run "no_candidates"; P9 still runs (publishes failure report) |
| Vina fails for a candidate | Skip that candidate; log |
| LLM brief generation fails | Use templated fallback |
| Biologic candidate has no SMILES for Vina | Skip Vina; use ipTM directly for stability proxy |

---

## 11. Performance Characteristics

| Step | Typical time | Notes |
|---|---|---|
| Triple Vina per SM candidate (exhaustiveness=12) | ~2 min | 3 runs × ~40s each |
| Scorecard computation | < 1 s | CPU, pure math |
| LLM brief per candidate | ~10 s | LM Studio local |
| **Total (20 candidates)** | **~45 min** | Dominated by Vina |
