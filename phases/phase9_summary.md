# Phase 9 — Output Packaging & Reproducibility: Implementation Summary

**Written:** 2026-06-03  
**Status:** Code complete · Supabase Storage upload validated · self-audit and executive summary gates functional  
**Source:** `src/phases/phase9/` — `assembler.py`, `runner.py`  
**Bottlenecks log:** `bottlenecks/phase9.md`

---

## What Phase 9 Does

Phase 9 is the terminal phase of every RxDis run. It converts the accumulated in-memory phase outputs and Supabase database records into a self-contained, reproducible research package: a directory tree that can be zipped, archived, and inspected without any pipeline infrastructure. The package is uploaded to Supabase Storage so the React frontend can offer a one-click download. Two LLM gates run at this phase: a self-audit that checks the attrition funnel for anomalies, and an executive summary that writes a human-readable README.md. Finally, `runs.status` is set to `'completed'` and `runs.cost_actual` is recorded.

---

## File Map

```
src/phases/phase9/
├── __init__.py
├── runner.py       # 5-step orchestrator: assemble → audit → summary → zip → mark complete
└── assembler.py    # assemble_package(), zip_package(), upload_package(), _collect_version_pins()
```

---

## Step-by-Step Pipeline

### Step 9.1 — Directory Assembly

`assemble_package()` in `assembler.py` builds:

```
output/{disease_name}_{run_id[:8]}/
├── run_metadata.json          # Config, DB versions, timestamps
├── ranked_targets.json        # All targets from Phase 1 with evidence trails
├── targets/
│   └── {SYMBOL}/
│       ├── target_validation.json   # Phase 2 evidence summary
│       ├── pockets.json             # fpocket pocket descriptors
│       ├── candidates_repurposing.json
│       ├── candidates_de_novo_sm.json
│       ├── candidates_biologic.json
│       └── admet/
│           └── {cid}_admet.json     # Per-candidate ADMET subscores
├── compute_log.json           # All compute_log rows for this run_id
├── decisions.json             # All LLM gate decisions (prompts redacted)
├── citations.bib              # Static BibTeX references
└── README.md                  # LLM-generated executive summary (Step 9.3)
```

The root directory name pattern is `{disease_name_snakecase}_{run_id[:8]}` — for example, `pancreatic_cancer_9f3a1b2c/`. This provides human-readable identification while the 8-char run_id prefix ensures uniqueness.

### Step 9.2 — LLM Self-Audit

Gate ID: `9_self_audit`

The LLM is given the attrition funnel counts from all phase outputs:

| Funnel metric | Source |
|---|---|
| `n_targets_p1` | `len(phase1_output["ranked_targets"])` |
| `n_targets_p2` | `phase2_output["n_passing"]` |
| `n_candidates_p4` | `phase4_output["n_candidates_total"]` |
| `n_passed_p8` | `phase8_output["n_candidates_passed"]` |

The LLM checks for:
- Unreasonable attrition (e.g. 20 targets → 0 candidates)
- Unexpected zero counts at any phase
- Cost or time anomalies
- Caveats to include in the final report

**Schema:**
```json
{
  "audit_passed": true,
  "concerns": [],
  "caveats_for_report": ["MD stability not computed...", "..."],
  "recommended_rerun": false
}
```

**Hard-coded safety check (LLM-independent):**
```python
if n_targets_p1 == 0:
    audit_result["audit_passed"] = False
    audit_result["concerns"].append("Phase 1 returned zero targets")
```

This check runs regardless of the LLM response, preventing a weak local model from marking a failed run as passed.

Temperature: 0.15, max_tokens: 400.

### Step 9.3 — Executive Summary (README.md)

Gate ID: `9_executive_summary`

The LLM writes a structured Markdown README with:
- **Overview:** disease, EFO ID, intent mode, indication type
- **Top Targets:** bullet list of top-5 Phase 1 ranked symbols
- **Key Findings:** number of validated candidates, pointer to per-target directories
- **Caveats & Limitations:** audit concerns + permanent caveats (MD not run, biologic scoring limitations)
- **Reproducibility:** exact `kickoff.py` command to re-run

If the LLM fails or returns unparseable JSON, a static template `_default_readme()` is used as fallback. The README is written to `{package_root}/README.md` before zipping.

Temperature: 0.3, max_tokens: 800.

### Step 9.4 — Zip + Supabase Storage Upload

`zip_package()` creates a `{run_name}.zip` alongside the directory using Python's built-in `zipfile.ZipFile(compression=ZIP_DEFLATED)`. The zip preserves the full relative path tree so it unpacks cleanly.

`upload_package()` uploads to:
```
Supabase Storage bucket: artifacts
Path: runs/{run_id}/package.zip
```

The upload logic uses a remove-then-upload pattern to handle overwrites:
```python
try:
    storage.from_("artifacts").upload(storage_path, data, ...)
except Exception:
    storage.from_("artifacts").remove([storage_path])
    storage.from_("artifacts").upload(storage_path, data, ...)
```

Returns a public URL (or `None` on failure). See Bottleneck H1 in `bottlenecks/phase9.md` for the silent-failure risk.

### Step 9.5 — Mark Run Completed

```python
db.table("runs").update({
    "status": "completed",
    "cost_actual": cost_actual,
    "updated_at": now_utc_iso(),
}).eq("id", run_id).execute()
```

`cost_actual` is computed by summing `cost_usd` from all `compute_log` rows for this `run_id`. This covers hosted API costs (Anthropic/OpenAI tokens, NIM API calls, CLUE API) but not local compute (Vina, sklearn, RDKit).

---

## Package Contents Reference

### `run_metadata.json`

```json
{
  "run_id": "9f3a1b2c-...",
  "disease": "pancreatic cancer",
  "efo_id": "EFO_0002618",
  "intent_mode": "full",
  "indication_type": "oncology",
  "through_phase": 9,
  "created_at": "2026-06-03T14:22:01.000Z",
  "db_versions": {
    "rdkit": "2026.3.2",
    "lightgbm": "4.3.0",
    "scikit-learn": "1.5.2",
    "xgboost": "2.0.3",
    "meeko": "0.7.1",
    "vina": "1.2.7",
    "openmm": "8.5.1",
    "scipy": "1.13.1",
    "numpy": "1.26.4",
    "chembl": "37",
    "lm_studio_model": "qwen3-8b-mlx",
    "primekg": "2023.10"
  },
  "config": {
    "target_count_max": 20,
    "candidates_per_target_max": 10,
    "seed_targets": ["KRAS"],
    "modality_preference": "auto",
    "llm_provider": "lmstudio"
  }
}
```

### `decisions.json`

Compact format — prompts are stripped for file size. Full prompts are in the `decisions` Supabase table:

```json
[
  {
    "phase": 1,
    "gate": "1.1_efo_disambiguation",
    "provider": "lmstudio",
    "model": "qwen3-8b-mlx",
    "decision": {
      "efo_id": "EFO_0002618",
      "confidence": 0.95,
      "reasoning": "Pancreatic ductal adenocarcinoma is the dominant histology..."
    }
  }
]
```

### `compute_log.json`

```json
[
  {
    "run_id": "9f3a1b2c-...",
    "phase": 4,
    "step": "vina_dock_KRAS",
    "service": "local",
    "wall_time_s": 284.1,
    "cost_usd": 0.0,
    "created_at": "..."
  },
  {
    "run_id": "9f3a1b2c-...",
    "phase": 1,
    "step": "phase1_literature_extraction",
    "service": "anthropic",
    "wall_time_s": 42.3,
    "cost_usd": 0.0034,
    "created_at": "..."
  }
]
```

### `citations.bib`

Static BibTeX file bundled in `assembler.py`. Includes:
- Pushpakom et al. 2019 (Drug repurposing review, Nature Reviews Drug Discovery)
- Ertl & Schuffenhauer 2009 (SAScore, Journal of Cheminformatics)
- Trott & Olson 2010 (AutoDock Vina, Journal of Computational Chemistry)
- Zitzler & Thiele 1999 (Hypervolume indicator, IEEE TEC)
- Lipinski 2001 (Rule of Five, J Pharmacol Toxicol Methods)
- McInnes et al. 2023 (PrimeKG, Scientific Data)

---

## Version Pinning Strategy

`_collect_version_pins()` uses `importlib.metadata.version(pkg)` at Phase 9 runtime to record the installed package versions. This is deliberately simple and best-effort:

| Package | Key | How pinned |
|---|---|---|
| `rdkit` | rdkit | `importlib.metadata.version("rdkit")` |
| `lightgbm` | lightgbm | `importlib.metadata.version("lightgbm")` |
| `scikit-learn` | scikit-learn | `importlib.metadata.version("scikit_learn")` |
| `xgboost` | xgboost | `importlib.metadata.version("xgboost")` |
| `meeko` | meeko | `importlib.metadata.version("meeko")` |
| `vina` | vina | `importlib.metadata.version("vina")` |
| `openmm` | openmm | `importlib.metadata.version("openmm")` |
| `scipy` | scipy | `importlib.metadata.version("scipy")` |
| `numpy` | numpy | `importlib.metadata.version("numpy")` |
| ChEMBL | chembl | Parsed from `DB_CHEMBL/chembl_{N}.db` filename |
| LM Studio model | lm_studio_model | `settings.LMSTUDIO_MODEL` env var |
| PrimeKG | primekg | Hard-coded "2023.10" (release date of current kg.csv) |

See Bottleneck H4 in `bottlenecks/phase9.md` for the limitation that `importlib.metadata` reports the installed version at packaging time, not the version actually used to generate results (which could differ if the venv was updated mid-run).

---

## Self-Audit Attrition Logic

Expected attrition at each phase in a normal run:

| Transition | Expected attrition | Anomaly flag |
|---|---|---|
| P1 targets → P2 validated | 20–40% attrition | > 75% attrition is suspicious |
| P2 validated → P4 candidates | 0% attrition (all validated targets get candidates) | 0 candidates from > 0 targets is a bug |
| P4 candidates → P8 passed | 30–60% attrition | 100% failure may indicate scoring calibration issue |
| P8 passed → output | 0% attrition (all passed candidates are packaged) | N/A |

The LLM self-audit checks for these patterns and populates `caveats_for_report` — which are then included verbatim in the README.md executive summary.

---

## Output Contract

```json
{
  "package_path": "/home/rohanvyas/Documents/AI Scientist/output/pancreatic_cancer_9f3a1b2c.zip",
  "package_url": "https://{supabase-url}/storage/v1/object/public/artifacts/runs/9f3a1b2c-.../package.zip",
  "ranked_targets_count": 20,
  "candidates_total": 94,
  "cost_actual_usd": 0.0421,
  "audit": {
    "audit_passed": true,
    "concerns": [],
    "caveats_for_report": [
      "MD stability not computed — Vina re-dock CV used as proxy",
      "Biologic candidates scored by developability; no AF2 ipTM without NIM key"
    ],
    "recommended_rerun": false
  },
  "reproducibility": {
    "rdkit": "2026.3.2",
    "lightgbm": "4.3.0",
    ...
  },
  "wall_time_s": 28.4
}
```

---

## Performance Notes

Phase 9 is purely I/O-bound:
- DB reads (targets, candidates, compute_log, decisions): typically 0.5–3 s
- File writes (JSON serialization for 20+ targets, 100+ candidates): 1–5 s
- Zip creation: 0.5–2 s depending on total package size
- Supabase Storage upload: 2–20 s depending on file size and network
- LLM gates (self-audit + summary): 5–30 s depending on model

Total typical wall time: **20–60 seconds** for a standard 5-target run.

---

## Known Limitations and Bottleneck Cross-References

See `bottlenecks/phase9.md` for full analysis. Key issues:

- **H1 (yellow):** Upload failure is silent — run is marked `completed` even if Supabase Storage rejects the upload.
- **H2 (yellow):** `decisions.json` strips prompts — full audit trail requires querying Supabase `decisions` table directly.
- **H3 (yellow):** Self-audit quality depends on LLM model — weak local models may miss obvious attrition anomalies.
- **H4 (green):** Version pinning records installed versions at packaging time, not versions used during data generation.
- **H5 (green):** `citations.bib` is static — target-specific recent literature is not included.
