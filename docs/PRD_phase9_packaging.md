# PRD — Phase 9: Output Packaging & Reproducibility

**Maps to:** Human Pipeline.md §PHASE 9
**Celery queue:** `cpu` + `llm` (self-audit)
**Depends on:** Phase 8 final scorecards

---

## Goal

Assemble a **reproducible, documented, downloadable package** of the entire run: ranked targets, per-target candidates (repurposing / de novo SM / biologic), poses, ADMET, citations, compute log, and pinned versions. Run a final LLM self-audit before publishing.

---

## Inputs Required From You

### Software (local)
- conda env `rxdis`: standard Python (json, zipfile), `pybtex` or manual `.bib` writer
- LM Studio server live (self-audit)
- Docker (to emit the reproducibility Dockerfile + environment.yml)

### Databases / APIs
- None — consumes prior phase outputs + Supabase artifacts.

### From config
- `output_dir` (logical package name)
- `exclude_drugs` (final prune safety check)

---

## Process Steps

### 9.1 Assemble directory tree
```
output/{run_name}/
├── run_metadata.json     (disease, EFO, timestamp, DB versions, model commits, config)
├── ranked_targets.json
├── targets/{symbol}/
│   ├── target_validation.json
│   ├── structure.pdb
│   ├── pockets.json
│   ├── candidates_repurposing.json
│   ├── candidates_de_novo_sm.json
│   ├── candidates_biologic.json
│   ├── poses/{cid}_pose.pdb + _md_summary.json
│   └── admet/{cid}_admet.json
├── citations.bib
├── compute_log.json
├── decisions.json        (all LLM gate decisions + any human overrides)
└── README.md
```

### 9.2 Reproducibility pinning
- Pin OT release tag, ChEMBL version, AFDB v4, PrimeKG release, Boltz-2 commit, REINVENT4 version, LM Studio model id.
- Persist exact GraphQL queries used.
- Emit `Dockerfile` + `environment.yml` (from `requirements.txt` + conda spec).

### 9.3 Compute + decision logs
- `compute_log.json` from the `compute_log` table (per-step cost/time/service).
- `decisions.json` from the `decisions` table (full LLM audit trail).

### 9.4 Package + upload
- Zip the tree → upload to Supabase Storage `runs/{run_id}/package.zip`.
- Mark `runs.status = completed`, set `runs.cost_actual`.

---

## Local-LLM Decision Points

| Gate | Decision | Output schema |
|---|---|---|
| `9_self_audit` | audit counts/attrition/failure-modes/cost reasonableness; caveats for report; rerun? | `{audit_passed,concerns[],caveats_for_report[],recommended_rerun}` |
| `9_executive_summary` | write the README.md exec summary (disease, top candidates, confidence, caveats) | `{readme_markdown}` |

---

## I/O Contract

**Input:** Phases 1–8 outputs + DB version pins + compute/decision tables.

**Output (`phase_results.output_json` for phase 9):**
```json
{
  "package_path":"runs/{run_id}/package.zip",
  "ranked_targets_count":20,
  "candidates_total":34,
  "cost_actual_usd":42.5,
  "audit":{"audit_passed":true,"caveats_for_report":["Tdark target X speculative"]},
  "reproducibility":{"ot_release":"24.03","chembl":"34","model":"qwen/qwen3-4b-thinking-2507"}
}
```

---

## Success Criteria

1. `package.zip` downloadable from the UI and contains the full tree.
2. All version pins present in `run_metadata.json`.
3. `decisions.json` contains every LLM gate decision across all phases.
4. Self-audit catches anomalous attrition (e.g., 20 targets → 1 candidate) and flags it.
5. `exclude_drugs` confirmed absent from final candidates.
6. Re-running with the same config + pinned DBs reproduces the top-10 targets.

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| Zero candidates >0.5 across run | publish "no candidates + failure modes" report (per spec) |
| Self-audit flags critical anomaly | mark `recommended_rerun=true`; surface in UI; do not silently publish |
| Storage upload fails | retry; keep local copy; mark run `completed` only after upload confirmed |
