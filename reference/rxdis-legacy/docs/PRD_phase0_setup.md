# PRD — Phase 0: System Setup & Health Checks

**Maps to:** Human Pipeline.md §PHASE 0
**Celery queue:** `cpu` (health checks), runs once per run before any phase
**Depends on:** RunConfig (Master PRD §5)

---

## Goal

Before any compute is spent, guarantee the run *can* succeed: validate every credential, confirm every required database/tool is present and at a pinned version, probe every hosted endpoint for availability, and — if `dry_run=true` — produce a cost estimate and a go/no-go report **without running real compute**.

This phase is the gatekeeper. Per the source spec: *"if hosted accounts are not all provisioned, do NOT proceed."*

---

## Inputs Required From You

### Software (local, one-time, conda env `rxdis` on Python 3.10)
- conda/mamba installed
- The `rxdis` conda environment created (see `requirements.txt`)
- LM Studio installed, `qwen/qwen3-4b-thinking-2507` downloaded, **local server running** at `http://localhost:1234`
- Redis running (`redis-server` or docker)
- Supabase project created (cloud or self-hosted); schema migrated

### Databases (local downloads — you are already mid-download in `Databases/`)
| DB | Local path expected | Pinned version field |
|---|---|---|
| PrimeKG | `Databases/primekg/{nodes.csv,edges.csv}` | release tag |
| DepMap | `Databases/depmap/CRISPR_gene_effect.csv` | release quarter |
| STRING | `Databases/string/9606.protein.links.v12.0.txt` | v12.0 |
| BioGRID | `Databases/biogrid/*.tab3.txt` | build number |
| GTEx | `Databases/gtex/*_gene_tpm.gct.gz` | v8/v10 |
| AlphaMissense | `Databases/alphamissense/AlphaMissense_hg38.tsv.gz` | v1 |
| ChEMBL | `Databases/chembl/` (SQLite optional) | version 34/35 |
| Human Protein Atlas | `Databases/human_protein_atlas/` | release |
| GWAS Catalog | `Databases/gwas_catalog/` | release date |

> Enamine REAL drug-like slice (~5 GB) is needed by Phase 5 only — can be deferred if `intent_mode=repurpose`.

### Accounts / API keys (put in `.env`)
| Service | Env var | Required for |
|---|---|---|
| Supabase | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY` | always |
| Redis | `REDIS_URL` | always |
| **LLM provider** (one of) | per-run key/URL — Anthropic key, OpenAI key, or `LMSTUDIO_BASE_URL` | always (user-selected; see `PRD_llm_provider_layer.md`) |
| NVIDIA NIM | `NIM_API_KEY` | Phases 2,4,5,6 |
| Neurosnap | `NEUROSNAP_API_KEY` | Phases 4,5,6,8 |
| AlphaFold Server | `AFSERVER_*` (Google session/cookie or API if available) | Phases 2,6 |
| Modal | `MODAL_TOKEN` | Phases 2,8 |
| RunPod | `RUNPOD_API_KEY` | Phases 5,8 |
| CLUE.io | `CLUE_API_KEY` | Phase 4 |
| OMIM | `OMIM_API_KEY` | Phase 1 |
| NCBI E-utils | `NCBI_API_KEY` | Phase 1 |

> Which keys are *required* depends on `intent_mode`. `repurpose` doesn't need RunPod/de-novo services; `dry_run` reports exactly which are missing for the chosen mode.

---

## Process Steps

### 0.1 Validate RunConfig
- Parse + validate against the Pydantic `RunConfig` model (Master PRD §5).
- Resolve `intent_mode` → required services set (Master PRD §5.1).
- Reject with clear errors if required fields malformed.

### 0.2 Credential validation
- For each required service (per intent mode), perform a cheap auth probe:
  - **LLM provider (the selected one):**
    - `anthropic`: 1-token `messages` call → confirm key + model live.
    - `openai`: `GET /models` or 1-token completion.
    - `lmstudio`: `GET /v1/models` → confirm model id matches `llm.lmstudio.model`.
  - Supabase: select 1 from `runs` with service key.
  - NIM: list models / health endpoint.
  - Neurosnap, Modal, RunPod, CLUE, OMIM, NCBI: minimal authenticated ping.
- Record each as `{service, ok, latency_ms, detail}`.

### 0.3 Database presence + version pinning
- Confirm each required local DB file exists and is readable.
- Extract/record version (file header, release tag, or checksum) → stored in `runs.config.db_versions`.

### 0.4 Hosted endpoint health probes (deprecation guard)
- Per spec caveat #10: hosted models get deprecated. Probe each model endpoint actually used downstream (AlphaFold2 NIM, DiffDock NIM, RFdiffusion NIM, ProteinMPNN NIM, GenMol NIM, Boltz-2 Neurosnap, BoltzGen Neurosnap) and confirm it's live + not deprecated.
- Build the **active-reroute table** (which fallback to use if primary is down).

### 0.5 Cost estimate (always for dry_run, advisory otherwise)
- From the Compute Budget Table (Human Pipeline.md §Compute Budget) × the phases that will run under this `intent_mode` × `target_count_max` × `candidates_per_target_max`.
- Return `cost_estimate` written to `runs.cost_estimate`.

### 0.6 GPU / VRAM probe
- Detect local GPU + free VRAM. Set effective `GPU_SHARING_MODE`.
- Warn if LM Studio resident model + planned local MD would exceed VRAM → recommend RunPod burst.

---

## Local-LLM Decision Points

| Gate | Decision | Output |
|---|---|---|
| `0.dryrun_summary` | Given the health-check results + cost estimate + missing creds, write a plain-English go/no-go recommendation for the user | `{recommendation: go|fix_first|no_go, blockers[], warnings[], summary}` |

(Phase 0 is mostly deterministic checks; the LLM only summarizes the report for the UI.)

---

## I/O Contract

**Input:** `RunConfig` (Master PRD §5)

**Output (`phase_results.output_json` for phase 0):**
```json
{
  "credentials": [{"service":"NIM","ok":true,"latency_ms":210}],
  "databases":   [{"name":"PrimeKG","present":true,"version":"2.1"}],
  "endpoints":   [{"model":"alphafold2-nim","live":true,"deprecated":false}],
  "reroute_table": {"alphafold2-nim":["esmfold-nim","colabfold"]},
  "gpu": {"name":"RTX 3050","vram_gb":6,"sharing_mode":"lmstudio_resident"},
  "cost_estimate_usd": 38.5,
  "missing_required": [],
  "go_no_go": "go"
}
```

---

## Success Criteria

1. With all creds present, returns `go_no_go: "go"` and a cost estimate.
2. With a missing required key (for the chosen mode), returns `no_go` and names exactly the missing service(s).
3. `dry_run=true` runs **zero** real compute and **zero** hosted inference cost.
4. All DB versions recorded in `runs.config.db_versions` for reproducibility.
5. Deprecated hosted model is detected and its reroute populated.

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| LM Studio not running | Hard block — instruct user to start LM Studio server |
| Required DB missing | Hard block — name the file + download URL from registry |
| Required key missing | Hard block (for that mode) — name service |
| Hosted endpoint deprecated | Auto-populate reroute; warn; proceed |
| VRAM insufficient for plan | Warn + set `GPU_SHARING_MODE=lmstudio_resident`, route MD to RunPod |
