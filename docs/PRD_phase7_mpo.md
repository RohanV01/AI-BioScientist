# PRD — Phase 7: Multi-Parameter Lead Optimization (MPO)

**Maps to:** Human Pipeline.md §PHASE 7
**Celery queue:** `gpu` (BoTorch GP on local GPU), `cpu`/`hosted` (re-evaluation via P5/P6 steps), `llm`
**Depends on:** Phase 5 (`de_novo_sm`) and/or Phase 6 (`biologic`) candidates

---

## Goal

Jointly optimize each candidate across multiple objectives (potency, selectivity, ADMET/developability, novelty, SA) using Bayesian active learning, rather than ranking on affinity alone. Produce a Pareto-optimal candidate set for the final validation gate.

---

## Inputs Required From You

### Software (local)
- conda env `rxdis`: BoTorch, GPyTorch (fit comfortably on 6 GB GPU)
- REINVENT4 (SM candidate generation biased by GP) — reused from Phase 5
- LM Studio server live

### Databases / APIs
- Re-evaluation reuses Phase 5.4–5.5 (ADMET, docking, Boltz-2) and Phase 6.3–6.5 (refold, developability) — same accounts (NIM, Neurosnap, ADMETlab).

### From config
- `budget_hosted_usd` (stops loop when exhausted)
- `indication_type` (objective weighting)

---

## Process Steps (per target candidate set)

### 7.1 Desirability function
- BoTorch Gaussian Process over: potency, selectivity, ADMET, novelty, developability, SA.
- Produce Pareto front + scalar desirability.

### 7.2 Active-learning loop
- Acquisition: qNEHVI (multi-objective).
- 3–5 iterations:
  1. Suggest 20 candidates (REINVENT4 GP-biased for SM; backbone mutations for biologics).
  2. Evaluate (Phase 5.4–5.5 for SM, Phase 6.3–6.5 for biologics).
  3. Update GP, re-rank.
- Stop: Pareto hypervolume improvement <1% OR 100 evaluated OR budget exhausted.

---

## Local-LLM Decision Points

| Gate | Decision | Output schema |
|---|---|---|
| `7.2_iteration_review` | what chemical/sequence space is being explored; explore/exploit balance vs remaining budget; flag unreasonable suggestions | `{space_explored,balance_assessment,flagged_unreasonable[],recommendation}` |

---

## I/O Contract

**Input:** Phase 5/6 candidate sets.

**Output (`phase_results.output_json` for phase 7):**
```json
{"optimized":{
  "LRRK2":{"pareto_front":[{"id":"DNSM_047","desirability":0.88,
            "objectives":{"potency":-9.4,"admet":0.82,"sa":2.7,"selectivity":0.9}}],
           "iterations_run":4,"hypervolume_final":0.71}
}}
```
Updates `candidates.subscores` with optimized objective values.

---

## Success Criteria

1. Binding-ranking reproducible across two independent runs.
2. Loop stops correctly on hypervolume plateau, count cap, or budget.
3. GP never extrapolates into chemically unreasonable space without an LLM flag.
4. Optimized candidates dominate (Pareto) their pre-optimization parents.

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| No improvement after 1 iteration | halt; pass best parents forward |
| Budget exhausted mid-loop | stop, keep current Pareto front, warn |
| GP suggests nonsense | LLM flag drops them; re-suggest |
