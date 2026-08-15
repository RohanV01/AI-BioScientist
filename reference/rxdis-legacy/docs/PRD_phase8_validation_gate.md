# PRD — Phase 8: In-Silico Validation Gate

**Maps to:** Human Pipeline.md §PHASE 8
**Celery queue:** `gpu` (local MD), `hosted` (RunPod MD burst, Modal FEP, Neurosnap Boltz-ABFE), `cpu` (gmx_MMPBSA), `llm`
**Depends on:** Phase 7 optimized candidates (top 5–10 per target)

---

## Goal

The toughest filter: confirm that top candidates **stay bound** (MD pose stability) and bind **tightly enough** (free-energy refinement). Only candidates passing here become final output. Compute-expensive → run only top 5–10 per target.

---

## Inputs Required From You

### Software (local)
- conda env `rxdis`: GROMACS (RTX 3050 ~14 ns/day), OpenMM (memory-efficient alt), gmx_MMPBSA, PMX (FEP, hosted recommended)
- LM Studio server live

### Databases / APIs
- None new.

### Accounts / APIs
- RunPod (A100 MD burst, ~$1.39/hr) — `RUNPOD_API_KEY`
- Modal (PMX relative FEP, ~$2–5/pair) — `MODAL_TOKEN`
- Neurosnap (Boltz-ABFE absolute FEP) — `NEUROSNAP_API_KEY`

### From config
- `indication_type` (final scorecard weighting)
- `selectivity_target` (off-target free-energy check)
- `budget_hosted_usd` (MD on RunPod vs local tradeoff)

---

## Process Steps (per top candidate)

### 8.1 Short MD pose stability
- GROMACS local (10 ns ≈ 17h on RTX 3050) OR OpenMM 10–50 ns OR burst to RunPod A100 (~1h, ~$1.40).
- Drop if ligand RMSD >3 Å sustained >30% of trajectory.

### 8.2 Binding free-energy refinement
- gmx_MMPBSA local: single-trajectory MM-GBSA on 10 ns (~30 min/ligand).
- Top 3: PMX relative FEP on Modal A100 (~$2–5/pair).
- Absolute FEP: Boltz-ABFE (Neurosnap).
- Gate: ΔG < −8 kcal/mol (~µM Ki) for SM; ipTM >0.8 for biologics in lieu of FEP.

### 8.3 Final scorecard
- Combined score, default weights (adjusted by `indication_type`):
  0.30 binding + 0.20 stability + 0.20 ADMET/developability + 0.15 selectivity + 0.10 novelty + 0.05 modality_alignment.

---

## Local-LLM Decision Points

| Gate | Decision | Output schema |
|---|---|---|
| `8.1_md_interpretation` | trajectory verdict beyond raw RMSD threshold (transient unbinding, H-bond loss) | `{verdict,concern_level,interpretation,recommendation}` |
| `8.3_candidate_brief` | full drug-candidate summary report for a medicinal chemist | `{title,verdict,evidence[],risks[],next_wetlab_experiment}` |

---

## I/O Contract

**Input:** Phase 7 optimized candidates.

**Output (`phase_results.output_json` for phase 8):**
```json
{
  "target_validation_score":0.79,
  "candidates":[
    {"id":"niclosamide","candidate_score":0.84,"combined_score":0.81,
     "subscores":{"binding_affinity":-9.8,"pose_stability":0.86,
                  "admet_or_developability":0.8,"selectivity":0.9,"novelty":0.2},
     "md":{"rmsd_avg":1.4,"verdict":"stable"},
     "brief":"..."}
  ]
}
```
Updates `candidates.combined_score`, `subscores`; trajectory summaries → Storage.

---

## Success Criteria

1. ΔG < −8 kcal/mol enforced for SM; ipTM >0.8 for biologics.
2. MD instability (RMSD >3 Å sustained) drops the candidate.
3. Transient-unbinding events caught by LLM beyond the hard RMSD rule.
4. Every surviving candidate has a medicinal-chemist brief.
5. `selectivity_target` off-target free-energy checked for top 3.

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| MD diverges on RTX 3050 | timestep → 1 fs; shorten to 5 ns; burst to RunPod A100 |
| gmx_MMPBSA fails on charged ligand | linear PB instead of nonlinear; or Boltz-ABFE hosted |
| Zero candidates pass for a target | abort that target, proceed to next |
| Zero candidates pass for ALL targets | loop back to P5/6 relaxed (max 2 outer iterations) |
