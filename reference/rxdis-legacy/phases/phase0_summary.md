# Phase 0 — Setup & Health Check: Implementation Summary

**Written:** 2026-06-03  
**Status:** Code complete · all checks implemented · go/no-go logic validated  
**Source:** `src/phases/phase0/` — `checks.py`, `runner.py`  
**Note:** This file was previously mislabeled as Phase 1 content. Correct content added 2026-06-03.

---

## What Phase 0 Does

Phase 0 is the mandatory preflight check that runs before any computation. It validates that all required infrastructure (databases, credentials, binaries, LLM provider) is present and reachable, estimates the compute cost for the run, and makes a `go` / `no_go` decision. A `no_go` decision halts the pipeline immediately with a human-readable error message before any billable API calls are made.

Phase 0 writes its output to `phase_results` and, on `go`, advances the run to Phase 1. On `no_go`, it writes `mark_phase_failed()` and the run remains in a failed state until the operator fixes the missing resource.

---

## File Map

```
src/phases/phase0/
├── __init__.py
├── runner.py     # run_phase0(): orchestrates all checks, go/no-go decision, LLM summary
└── checks.py     # check_all_databases(), probe_*() functions, probe_gpu()
```

---

## Checks Performed

### Step 0.1 — RunConfig Validation

RunConfig is validated by Pydantic at construction time (before Phase 0 runs). By the time Phase 0 executes, the config is guaranteed structurally valid. Phase 0 does not re-validate config fields.

### Step 0.2 — Credential Probes

Each probe returns `{service, ok, latency_ms, detail}`. Probes are executed in order; failed probes are recorded but do not immediately halt the check (the go/no-go decision aggregates all results).

| Service | Function | Required? | How checked |
|---|---|---|---|
| **Supabase** | `probe_supabase()` | Yes | `db.table("runs").select("id").limit(1)` — tests connectivity and schema |
| **Redis** | `probe_redis()` | Yes | `redis.ping()` on `settings.REDIS_URL` |
| **LMStudio** | `probe_lmstudio()` | Yes (if provider=lmstudio) | GET `/models` endpoint, check model ID present |
| **Anthropic** | `probe_anthropic()` | Yes (if provider=anthropic) | `client.messages.create(max_tokens=1)` minimal call |
| **OpenAI** | `probe_openai()` | Yes (if provider=openai) | `client.models.retrieve(model)` — avoids billable text generation |
| **NVIDIA NIM** | `probe_nim()` | No (optional) | GET NVCF functions endpoint with Bearer token |
| **NCBI EUtils** | `probe_ncbi()` | No (optional) | ESearch with 1-result PubMed query |
| **OMIM** | `probe_omim()` | No (optional) | GET entry endpoint with MIM number 100050 |
| **Open Targets** | `probe_open_targets()` | No | GraphQL meta query (no auth required) |

LLM provider probes are conditional on `config.llm.provider` — only the configured provider is probed, not all three.

Optional probes (NIM, NCBI, OMIM) only run when their respective API keys are set in environment variables. A missing optional credential is noted in `credentials` but does not affect `go_no_go`.

### Step 0.3 — Database Presence Checks

`check_all_databases()` checks for the presence of each required local database file. It does **not** validate the contents of the database — only that the file exists and is readable (via `Path.exists()`). File size is reported in MB.

| Database | Path pattern | Required? | Version hint |
|---|---|---|---|
| **PrimeKG** | `DB_PRIMEKG/kg.csv` or `nodes.csv` | Yes | "combined_kg.csv" or "split nodes/edges" |
| **DepMap** | `DB_DEPMAP/CRISPRGeneEffect.csv` | Yes | CRISPRGeneEffect |
| **STRING** | `DB_STRING/9606.protein.links.detailed.v12.0.txt` | Yes | v12.0 |
| **BioGRID** | `DB_BIOGRID/*.tab3.txt` (any) | Yes | Detected from filename |
| **GTEx** | `DB_GTEX/*_gene_tpm.*` (any) | Yes | v11 |
| **AlphaMissense** | `DB_ALPHAMISSENSE/AlphaMissense_hg38.tsv` | Yes | v1 |
| **ChEMBL** | `DB_CHEMBL/chembl_37.db` (or any `chembl_*.db`) | Yes | 37 |
| **GWAS Catalog** | `DB_GWAS/*associations*.tsv` | Yes | latest |

**GWAS special case:** If only the studies TSV is present (not the associations TSV), a warning is added to the database entry: `"Only studies TSV present; download 'All associations' for full Phase 1 support"`. This is a degraded state — Phase 1 genetic evidence will run but the GWAS signal will be incomplete.

### Step 0.4 — NIM Hosted Endpoint Health

For runs with `NIM_API_KEY` set, Phase 0 checks each NVIDIA NIM model endpoint for availability and deprecation:

| NIM Model | Used in Phase | Purpose |
|---|---|---|
| `alphafold2-nim` | Phase 2 | Protein structure prediction |
| `diffdock` | Phase 4 | Neural docking (DiffDock stub) |
| `rfdiffusion` | Phase 6 | Protein backbone generation |
| `proteinmpnn` | Phase 6 | Sequence design on generated backbone |
| `genmol` | Phase 5 | de-novo SM generation |

A 404 response → `deprecated = True` → recorded in output. Deprecated NIM endpoints cause fallback to local alternatives (fpocket→Vina for docking; BRICS for SM generation; LLM peptide generation for biologics) — the pipeline does not fail, but cloud-accelerated paths are unavailable.

### Step 0.5 — Cost Estimation

Per-phase cost estimates (from pilot runs, not dynamically calculated):

| Phase | Median cost (USD) | Notes |
|---|---|---|
| 1 | $0.50 | PubMed abstracts + LLM literature extraction |
| 2 | $8.00 | NIM AlphaFold2 calls (dominant cost if NIM used) |
| 3 | $0.50 | Local modality selection |
| 4 | $5.00 | NIM DiffDock or local Vina + ChEMBL queries |
| 5 | $12.00 | GenMol NIM or BRICS de novo + ADMET |
| 6 | $8.00 | BoltzGen biologic generation |
| 7 | $1.00 | GP MPO (local sklearn + ADMET re-scoring) |
| 8 | $3.00 | Triple Vina re-dock + LLM briefs |
| 9 | $0.50 | LLM summary + packaging |

The total estimate is scaled by target count: `cost_estimate = sum(phase_costs) × max(1, target_count_max / 5)`. This is a rough approximation — actual cost depends heavily on whether NIM is used and on LLM token consumption for literature-rich diseases.

**Local-only runs (`llm_provider=lmstudio`, no NIM_API_KEY):** `cost_estimate_usd = $0.00` — all compute is local.

### Step 0.6 — GPU Probe

`probe_gpu()` calls `nvidia-smi --query-gpu=name,memory.free --format=csv,noheader,nounits` to detect available GPUs and free VRAM. Reports:

```json
{
  "gpus": [{"name": "NVIDIA GeForce RTX 3050 Laptop GPU", "vram_free_mb": 3200}],
  "sharing_mode": "exclusive"
}
```

The `GPU_SHARING_MODE` setting (from `settings.py`) is also reported. This informs downstream phases about GPU availability for OpenMM MD stubs (Phase 8) and local LLM inference via LMStudio.

---

## Go / No-Go Decision

The go/no-go aggregation logic:

```python
missing_required = []

# LLM reachability
llm_ok = any(cred["ok"] for cred in credentials 
             if cred["service"] in ("LMStudio", "Anthropic", "OpenAI"))
if not llm_ok:
    missing_required.append("LLM provider (LMStudio/Anthropic/OpenAI)")

# Redis
redis_ok = next((c["ok"] for c in credentials if c["service"] == "Redis"), False)
if not redis_ok:
    missing_required.append("Redis")

# Required databases
required_dbs = ["PrimeKG", "STRING", "BioGRID", "GTEx", "AlphaMissense", "ChEMBL"]
for db in databases:
    if db["name"] in required_dbs and not db["present"]:
        missing_required.append(f"Database:{db['name']}")

go_no_go = "go" if not missing_required else "no_go"
```

**Notably absent from required list:**
- GWAS Catalog: optional (degraded P1 genetic evidence if missing)
- DepMap: absent from required list in code, but strongly recommended
- NIM API key: entirely optional
- Open Targets: Phase 1 queries the live OT API, not a local file — if OT is down, P1 will fail at runtime rather than Phase 0

**On `no_go`:**
- `mark_phase_failed()` is called in the DB
- The output includes `missing_required` list
- The LLM summary (if reachable) says exactly what to fix
- Static summary fallback: `"Pipeline cannot proceed. Missing required: {items}. Fix these before starting a run."`

---

## LLM Summary Gate

If the LLM provider is reachable and `config.dry_run = False`, Phase 0 asks the LLM to summarize the health check results in 2–3 sentences:

```
Prompt:
  "You are a bioinformatics pipeline assistant. Summarize the following 
   health-check results in 2-3 plain English sentences for the user.
   Verdict: {go_no_go}
   Cost estimate: ${cost:.2f}
   Failing credentials: {list}
   Missing databases: {list}
   Give a go/fix_first/no_go recommendation and name exactly what needs fixing."
```

This runs at `temperature=0.1`, `max_tokens=512`. The output is stored as `summary` in the Phase 0 output and displayed in the React frontend before the user confirms the run should proceed.

---

## Output Contract

```json
{
  "credentials": [
    {"service": "Supabase", "ok": true, "latency_ms": 142, "detail": "connected"},
    {"service": "Redis", "ok": true, "latency_ms": 2, "detail": "pong"},
    {"service": "LMStudio", "ok": true, "latency_ms": 210, "detail": "model 'qwen3-8b-mlx' live"},
    {"service": "OpenTargets", "ok": true, "latency_ms": 380, "detail": "OT 2025-12"},
    {"service": "NCBI_Eutils", "ok": true, "latency_ms": 620, "detail": "reachable, hits=45923"},
    {"service": "OMIM", "ok": false, "latency_ms": 10001, "detail": "timeout"}
  ],
  "databases": [
    {"name": "PrimeKG", "present": true, "version": "combined_kg.csv", "size_mb": 937.2},
    {"name": "DepMap", "present": true, "version": "CRISPRGeneEffect", "size_mb": 248.1},
    {"name": "STRING", "present": true, "version": "v12.0", "size_mb": 1420.3},
    {"name": "BioGRID", "present": true, "version": "BIOGRID-ORGANISM-Homo_sapiens-4.4.232", "size_mb": 312.4},
    {"name": "GTEx", "present": true, "version": "v11", "size_mb": 1803.5},
    {"name": "AlphaMissense", "present": true, "version": "v1", "size_mb": 5242.0},
    {"name": "ChEMBL", "present": true, "version": "37", "size_mb": 28800.0},
    {"name": "GWAS_Catalog_Associations", "present": true, "version": "latest", "size_mb": 139.0}
  ],
  "endpoints": [
    {"model": "alphafold2-nim", "live": null, "deprecated": null, "detail": "no NIM key"},
    {"model": "diffdock", "live": null, "deprecated": null, "detail": "no NIM key"}
  ],
  "gpu": {
    "gpus": [{"name": "NVIDIA GeForce RTX 3050 Laptop GPU", "vram_free_mb": 3200}],
    "sharing_mode": "exclusive"
  },
  "cost_estimate_usd": 0.0,
  "missing_required": [],
  "go_no_go": "go",
  "summary": "All credentials and databases validated. Estimated cost for local-only run: $0.00. Pipeline is ready to run."
}
```

---

## Resume Semantics

Phase 0 does not have resume semantics — it re-runs from scratch each time. All Phase 0 checks are stateless and idempotent (they only read state from the environment, never write it). Re-running Phase 0 for an in-progress run is safe and common (e.g., to verify that a missing database was correctly added before resuming Phase 1).

---

## Performance Notes

| Check | Typical latency |
|---|---|
| Supabase connectivity | 100–300 ms |
| Redis ping | 1–5 ms |
| LMStudio model probe | 100–500 ms |
| Anthropic/OpenAI probe | 300–1000 ms |
| Open Targets GraphQL | 200–600 ms |
| NCBI EUtils | 400–800 ms |
| OMIM REST | 300–700 ms |
| Database presence (all 8) | < 10 ms total (just filesystem stat() calls) |
| NIM endpoint check (5 models) | 3–10 s (network-bound) |
| LLM summary generation | 5–30 s (model-dependent) |

**Total Phase 0 wall time:** 10–45 seconds depending on network latency and whether NIM probes run.

---

## Acceptance Criteria

| Test | Expected result |
|---|---|
| All databases present, LLM reachable, Redis up | `go_no_go = "go"`, `missing_required = []` |
| ChEMBL absent | `go_no_go = "no_go"`, `missing_required = ["Database:ChEMBL"]` |
| LMStudio model not loaded | `go_no_go = "no_go"`, `missing_required = ["LLM provider (LMStudio/Anthropic/OpenAI)"]` |
| GWAS absent (associations TSV only) | `go_no_go = "go"` (GWAS not in required_dbs), warning in database entry |
| OMIM timeout | `go_no_go = "go"` (OMIM optional), noted in credentials |
| No GPU detected | `go_no_go = "go"` (GPU optional), `gpu = {"gpus": [], "error": "nvidia-smi not found"}` |
| NIM key present, endpoint 404 | `go_no_go = "go"`, endpoint entry has `deprecated=True` — fallback paths will be used |
