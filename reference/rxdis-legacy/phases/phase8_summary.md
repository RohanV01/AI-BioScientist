# Phase 8 — In-Silico Validation Gate: Implementation Summary

**Written:** 2026-06-03  
**Status:** Code complete · triple-Vina re-dock validated · MD stubs present but inactive  
**Source:** `src/phases/phase8/` — `scorecard.py`, `runner.py`  
**Bottlenecks log:** `bottlenecks/phase7_phase8.md`

---

## What Phase 8 Does

Phase 8 is the final computational gatekeeping step before output packaging. It takes the top-N candidates from Phase 7 (or Phase 4 for repurpose-only runs), subjects each small-molecule candidate to three independent Vina re-docking runs at higher exhaustiveness than any prior phase, computes a 6-axis validation scorecard, and generates a medicinal chemist brief via LLM for each candidate that passes the combined-score threshold.

Molecular dynamics (MD) stability analysis has been intentionally deferred pending GROMACS installation or a RunPod burst session. In place of true RMSD-based stability, Phase 8 estimates binding mode consistency via the coefficient of variation (CV) of Vina scores across the three independent docking runs — a lower CV implies a more reproducible, and therefore presumably more stable, binding pose.

---

## File Map

```
src/phases/phase8/
├── __init__.py
├── runner.py      # Orchestrator: candidate gathering, re-docking, LLM briefs, DB writes
└── scorecard.py   # compute_final_score(), _pose_stability_from_multi_run(), rank_final_candidates()
```

---

## Candidate Sourcing

Candidates are gathered in priority order:

1. **Phase 7 Pareto front** — `phase7_output["optimized"][symbol]["pareto_front"]` for each target symbol
2. **Phase 4 repurposing** — `phase4_output["repurposing"][symbol]` for repurpose-only runs where P5/P6/P7 did not run
3. **DB fallback** — queries the `candidates` table ordered by `combined_score DESC` when neither P7 nor P4 output is available in memory

The top `P8_TOP_N` (default 5, configurable) candidates per target are selected. The `P8_TOP_N` cap is applied after the priority merge — if P7 has 18 Pareto-front members for a target, only the top 5 by desirability proceed to Phase 8.

---

## Triple Vina Re-Docking

Each SM candidate is re-docked **three independent times** using the same Phase 4 docking infrastructure (`src/phases/phase4/docking.py`).

### Why Three Runs?

AutoDock Vina uses a stochastic search (iterated local search with Monte Carlo moves, Trott & Olson 2010). Different random seeds can occasionally find different binding modes, particularly in large or flexible pockets. Running three times at higher exhaustiveness increases confidence that the reported binding mode is not a single-seed artifact.

### Exhaustiveness Comparison

| Phase | Exhaustiveness | Purpose |
|---|---|---|
| Phase 4 Tier 2 virtual screen | 4 | Fast throughput for ~400–800 compounds |
| Phase 4 Tier 1 / Phase 5 re-dock | 8 | Better coverage for known-mechanism drugs |
| **Phase 8** | **12** | Final validation — thorough pose sampling |

Exhaustiveness 12 requires approximately 3× more compute than exhaustiveness 4 (linear scaling, Trott & Olson 2010 Supplementary). At this exhaustiveness level, the false-minimum rate in benchmarks against crystal structures is typically < 10% for drug-sized molecules in well-defined pockets.

### Pose Stability Score

The coefficient of variation (CV) of the three Vina scores is used as a stability proxy:

```python
cv = abs(stdev(vina_scores) / mean(vina_scores))

# Mapping:
# CV < 0.05 → excellent stability → score ≈ 1.0
# CV = 0.05 → score = 1.0
# CV = 0.30 → score = 0.0
# Linear between: stability = max(0, min(1, 1 - (cv - 0.05) / 0.25))
```

If fewer than 2 valid runs are available (receptor prep failed, ligand prep failed, or biologic candidate), a neutral stability score of 0.5 is assigned.

**Important caveat:** This measure reflects Vina's internal reproducibility, not true thermodynamic pose stability. A compound with very reproducible Vina scores could still have a Kd >> 10 μM or unbind rapidly in MD. See Bottleneck H1 in `bottlenecks/phase7_phase8.md`.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `P8_TOP_N` | 5 | Candidates taken per target from P7 Pareto front |
| `P8_EXHAUSTIVENESS` | 12 | Vina exhaustiveness for all P8 re-docks |
| `P8_WORKERS` | 4 | `ProcessPoolExecutor` workers for parallel docking |

---

## 6-Axis Final Scorecard — `scorecard.py`

### Weights

Derived from PRD §8.3 — reflect a standard computational medicinal chemistry prioritization hierarchy:

| Axis | Key | Weight | Rationale |
|---|---|---|---|
| Binding affinity | `binding_affinity` | **0.30** | Primary evidence for target engagement; the sine qua non of a drug candidate |
| Pose stability | `pose_stability` | **0.20** | Confirms the binding event is reproducible; a consistent pose suggests a defined binding mode |
| ADMET / Developability | `admet_or_developability` | **0.20** | Safety and absorption gatekeeping; a potent but toxic compound advances nothing |
| Selectivity | `selectivity` | **0.15** | Therapeutic window — differentiates therapeutic hits from pan-assay interference |
| Novelty | `novelty` | **0.10** | IP differentiation; secondary to activity but required for patentability |
| Modality alignment | `modality_alignment` | **0.05** | Manufacturing and clinical feasibility signal — lowest weight because it can be waived |

Total: 1.00

### Axis Calculation Details

**Binding affinity:**
- SM: `_norm_vina(vina_score)` where `vina_norm = clamp(vina / -10.0, 0, 1)`. The ceiling is −10.0 kcal/mol (vs −12.0 in Phase 4 — Phase 8 uses a more conservative ceiling because candidates have already been filtered).
- Biologic: uses `iptm` if available (from Phase 6 NIM/Boltz-2 ipTM output); falls back to `developability_score` as a binding proxy. This is a known limitation (see Bottleneck H4).

**Pose stability:**
- SM: computed from `vina_runs` list via CV method described above.
- Biologic: 0.5 (neutral) — no Vina docking for biologics.
- If only 1 valid Vina run: 0.5 (cannot estimate variation).

**ADMET / developability:**
- SM: `admet_score` from `candidate.get("admet_score")` or `candidate["admet"]["admet_score"]`
- Biologic: `developability_score` from Phase 6 `score_developability()`
- Default when missing: 0.5 (neutral)

**Selectivity:**
```
No selectivity_target → 1.0 (full marks)
selectivity_target set:
  disqualifying ADMET flags matching the off-target → 0.3
  admet["hERG"] == "high" → 0.5
  admet["hERG"] == "medium" → 0.8
  otherwise → 1.0
```

**Novelty:**
`novelty = 1.0 - min(1.0, tanimoto_to_approved)`, where `tanimoto_to_approved` is the maximum Tanimoto similarity to any FDA-approved drug (computed in Phase 5 by `score_admet()`).

**Modality alignment:**
```
p3_primary in {SM, PROTAC}:
  candidate kind in {de_novo_sm, repurposing, sm} → 1.0
  otherwise (e.g. biologic fed to SM-routed target) → 0.5

p3_primary in {AB, peptide, biologic}:
  kind in {biologic, peptide} → 1.0
  otherwise → 0.5

p3_primary unknown → 0.7 (neutral)
```

### Combined Score Formula

```python
combined_score = (
    0.30 * binding_affinity
  + 0.20 * pose_stability
  + 0.20 * admet_or_developability
  + 0.15 * selectivity
  + 0.10 * novelty
  + 0.05 * modality_alignment
)
```

### Pass Threshold

`combined_score >= 0.45` → `passed = True`

The 0.45 threshold was selected to reflect a "moderate confidence" criterion across all six axes simultaneously. A hypothetical candidate scoring exactly at threshold would have, for example: binding = 0.6, stability = 0.5, ADMET = 0.5, selectivity = 1.0, novelty = 0.5, modality = 1.0 → score = 0.18 + 0.10 + 0.10 + 0.15 + 0.05 + 0.05 = 0.63 — well above threshold. In practice, the threshold mainly filters out biologic candidates with poor developability or SM candidates with Vina scores in the -4 to -6 range.

---

## LLM Decision Gate — Candidate Brief

**Gate ID:** `8.3_brief_{symbol}`  
**Trigger:** For every candidate that passes the combined-score threshold

The LLM is asked to produce a 4-sentence medicinal chemist brief covering:
1. Why the candidate looks promising for the target
2. Key strengths versus standard-of-care
3. The biggest risk or caveat
4. The recommended first wet-lab experiment

**Schema:**
```json
{
  "title": "...",
  "verdict": "promising",
  "evidence": ["...", "..."],
  "risks": ["...", "..."],
  "next_wetlab_experiment": "..."
}
```

The parsed brief is assembled into a single string:
```
{title}. Verdict: {verdict}. Evidence: {evidence[0]}; {evidence[1]}. 
Risks: {risks[0]}; {risks[1]}. Next step: {next_wetlab_experiment}
```

If JSON parsing fails, the raw LLM text (truncated to 400 chars) is stored as `candidate_brief`.

Temperature: 0.2, max_tokens: 350.

---

## MD Hookpoints (Deferred)

The runner contains commented-out stubs for OpenMM and GROMACS MD:

```python
# def _run_md_openmm(pdb_url, ligand_smiles, symbol, n_steps=50000):
#     """OpenMM: activated when RUNPOD_API_KEY set. Would run 100 ns
#     and return RMSD trajectory. Drop criterion: RMSD > 3Å sustained > 30%."""
#     pass
```

**OpenMM** is installed (`openmm 8.5.1` in `.venv`) and could be used locally. The constraint is GPU memory — the RTX 3050 (4 GB VRAM) requires ~17 hours per compound for a 100 ns simulation with explicit solvent. At RunPod rates (~$0.35/hr for A100), a 100 ns explicit-solvent simulation costs approximately $1.40 per compound.

When `RUNPOD_API_KEY` is set, the stub would:
1. Submit a GROMACS job to RunPod
2. Poll for completion
3. Download the RMSD trajectory
4. Flag compounds where RMSD > 3 Å for > 30% of the trajectory as unstable

Without MD, the `md_note` field is set to `"MD skipped (no GROMACS); binding confirmed by Vina re-dock only"` in the DB.

---

## Database Writes

After scoring each target, the `candidates` table is updated:

```sql
UPDATE candidates
SET combined_score = ?,
    subscores = subscores || {
        "phase": 8,
        "final_rank": ?,
        "passed": ?,
        "candidate_brief": "...",
        "md_note": "MD skipped...",
        "binding_affinity": ?,
        "pose_stability": ?,
        "admet_or_developability": ?,
        "selectivity": ?,
        "novelty": ?,
        "modality_alignment": ?
    }
WHERE run_id = ? AND target_id = ?
```

---

## Output Contract

```json
{
  "validation": {
    "KRAS": {
      "candidates": [
        {
          "smiles": "C=CC(=O)N1...",
          "combined_score": 0.672,
          "passed": true,
          "final_rank": 1,
          "vina_score_final": -8.91,
          "vina_runs": [-8.91, -9.02, -8.87],
          "subscores": {
            "binding_affinity": 0.891,
            "pose_stability": 0.948,
            "admet_or_developability": 0.731,
            "selectivity": 1.0,
            "novelty": 0.612,
            "modality_alignment": 1.0
          },
          "weights_used": {
            "binding_affinity": 0.30,
            "pose_stability": 0.20,
            "admet_developability": 0.20,
            "selectivity": 0.15,
            "novelty": 0.10,
            "modality_alignment": 0.05
          },
          "md_note": "MD skipped (no GROMACS); binding confirmed by Vina re-dock only",
          "candidate_brief": "KRAS G12C inhibitor with allosteric pocket engagement. Verdict: promising. Evidence: vina_score -8.91 across 3 independent runs; CV 0.008 indicating highly reproducible binding mode. Risks: KRAS-specific — may not cover G12D/G12V mutations. Next step: SPR binding assay against recombinant KRAS G12C GDP-bound form."
        }
      ],
      "n_passed": 3,
      "n_failed": 2,
      "target_validation_score": 0.601
    }
  },
  "n_targets": 5,
  "n_candidates_passed": 14,
  "wall_time_s": 487.2
}
```

---

## Acceptance Criteria

A successful Phase 8 run should satisfy:

| Check | Expectation |
|---|---|
| Candidates for a target with good P7 Pareto front | At least 1 of top-5 passes (combined_score ≥ 0.45) |
| Pose stability for low-CV triple re-docks | stability score ≥ 0.8 when CV < 0.06 |
| hERG "high" penalty applied | selectivity score = 0.5 when hERG is flagged |
| Biologic modality alignment for AB-routed target | modality_alignment = 1.0 |
| Candidate brief generated for all passed | `candidate_brief` non-empty string |

---

## Known Limitations and Bottleneck Cross-References

See `bottlenecks/phase7_phase8.md` for detailed analysis. Key issues:

- **H1 (red):** MD stability absent — pose_stability score measures Vina reproducibility, not thermodynamic stability. A 0.20-weight axis is effectively measuring "Vina is self-consistent."
- **H2 (red):** No free-energy refinement — MM-GBSA or FEP required to verify Kd < 1 μM for confident candidates.
- **H3 (yellow):** P8_TOP_N=5 cap may discard good candidates. Raise with `P8_TOP_N=10` if compute budget allows.
- **H4 (yellow):** Biologic binding affinity uses developability_score as proxy when ipTM is unavailable.
