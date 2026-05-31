# Master PRD — In-Silico Agentic Drug Discovery Platform

**Document type:** Master Product Requirements Document
**Version:** 1.0
**Date:** 2026-05-30
**Owner:** rohan.vyas@nurix.ai
**Companion docs:** `PRD_phase0_setup.md` … `PRD_phase9_packaging.md`, `requirements.txt`
**Source spec:** `Human Pipeline.md` (the deterministic human-executable pipeline this product automates)

---

## 1. Product Summary

A web-based platform that takes a **disease name** as input and produces **ranked, in-silico-validated drug candidates** (small molecules, biologics, peptides) per target, with full evidence trails. It automates the 10-phase pipeline defined in `Human Pipeline.md`, replacing human decision gates with a **user-selectable LLM backend** (Anthropic Claude, OpenAI, or a local LM Studio model such as `qwen/qwen3-4b-thinking-2507`) wherever judgment is needed, and routing heavy compute to free/cheap hosted services.

The platform is built from day one to **scale to multiple concurrent pipelines and multiple users**, with persistent state, resumable runs, and horizontal worker scaling.

### 1.1 What makes this different from a script

| Concern | Script (Human Pipeline.md) | This Platform |
|---|---|---|
| Execution | One disease, one terminal, blocking | Many diseases, many users, async |
| State | Files on disk, no recovery | Supabase-backed, fully resumable |
| Decisions | Human at each gate | Local LLM at each gate |
| Interface | CLI | Gradio web UI |
| Scale | 1 | Horizontal (add workers) |
| Cost control | Manual | `dry_run` cost estimation + budget gates |

---

## 2. Goals & Non-Goals

### 2.1 Goals
1. **End-to-end automation** of all 10 phases with local-LLM decision-making at every human gate.
2. **Multi-tenant, multi-pipeline** from the start — concurrent runs isolated per user/project.
3. **Resumable** — any run can resume from any completed phase (`resume_from_phase`).
4. **Cost-aware** — `dry_run` estimates spend and validates credentials before committing real compute.
5. **Pluggable LLM backend (per-user, per-run)** — reasoning/synthesis runs on Anthropic, OpenAI, or local LM Studio at the user's choice; local is free + fully offline-capable; the pipeline adapts strategy to the chosen provider's capabilities (see `PRD_llm_provider_layer.md`).
6. **Reproducible** — pinned DB versions, model versions, exact queries persisted per run.

### 2.2 Non-Goals (v1)
- Wet-lab integration or LIMS connectivity.
- Agentic/autonomous planning (the pipeline is deterministic & sequential per spec).
- Training/fine-tuning models.
- Real-time collaboration (multi-user editing of one run).
- Mobile UI.

---

## 3. Architecture Overview

### 3.1 High-level diagram

```
                          ┌─────────────────────────────┐
                          │         Gradio UI            │
                          │  (submit run, watch progress,│
                          │   review gates, download)    │
                          └───────────────┬──────────────┘
                                          │ HTTP
                          ┌───────────────▼──────────────┐
                          │      FastAPI API layer        │
                          │  /runs /runs/{id} /phases     │
                          │  auth, validation, dry_run    │
                          └───────────────┬──────────────┘
                                          │ enqueue
                          ┌───────────────▼──────────────┐
                          │     Redis  (Celery broker)    │
                          └───────────────┬──────────────┘
                                          │ dispatch tasks
          ┌──────────────────┬────────────┼────────────────┬─────────────┐
          ▼                  ▼             ▼                ▼             ▼
     ┌─────────┐       ┌─────────┐   ┌─────────┐      ┌─────────┐  ┌─────────┐
     │ Worker1 │       │ Worker2 │   │ Worker3 │ ...  │ WorkerN │  │ GPU     │
     │ (CPU)   │       │ (CPU)   │   │ (CPU)   │      │ (CPU)   │  │ Worker  │
     └────┬────┘       └────┬────┘   └────┬────┘      └────┬────┘  └────┬────┘
          │                 │             │                │            │
          └─────────────────┴──────┬──────┴────────────────┴────────────┘
                                    │ read/write state, artifacts
                          ┌─────────▼──────────┐
                          │      Supabase       │
                          │  Postgres + Storage │
                          │  + Auth + RLS       │
                          └─────────┬──────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
       ┌────────────┐       ┌──────────────┐      ┌──────────────┐
       │ LM Studio   │       │ Local tools  │      │ Hosted compute│
       │ (local LLM  │       │ RDKit, Vina, │      │ NIM, Neurosnap│
       │  decisions/ │       │ GROMACS,     │      │ AF Server,    │
       │  synthesis) │       │ fpocket...   │      │ Modal, RunPod │
       └────────────┘       └──────────────┘      └──────────────┘
```

### 3.2 Component responsibilities

| Component | Tech | Responsibility |
|---|---|---|
| **UI** | Gradio (Blocks) | Submit runs, live progress, gate review/override, artifact download |
| **API** | FastAPI + Pydantic | Validate config, enqueue jobs, serve status, `dry_run` estimation, auth |
| **Broker** | Redis | Celery message broker + result backend + rate-limit token buckets |
| **Workers** | Celery | Execute phases as tasks; CPU pool + dedicated GPU pool (concurrency=1) |
| **State/Storage** | Supabase (Postgres + Storage + Auth) | Run state, phase outputs, artifacts, user/project isolation (RLS) |
| **Reasoning** | Pluggable LLM provider (Anthropic / OpenAI / LM Studio) | All LLM decisions & synthesis via one provider-agnostic interface; capability-driven map-reduce (`PRD_llm_provider_layer.md`) |
| **Local tools** | conda/pip installed | RDKit, Vina, fpocket, GROMACS, OpenMM, REINVENT4, ProteinMPNN, etc. |
| **Hosted compute** | HTTP clients | NIM, Neurosnap, AlphaFold Server, Modal, RunPod, ADMETlab, CLUE.io |

### 3.3 Why Celery + Redis (vs. alternatives)
- Runs are **long** (up to ~36h) and **bursty** — a queue with horizontal workers fits naturally.
- **Resume/retry** is first-class (Celery task retries + our own phase-level checkpointing in Supabase).
- **GPU contention** is handled with a dedicated Celery queue (`gpu`) with `worker_concurrency=1` so only one MD/folding job touches the local 6 GB GPU at a time, while CPU phases parallelize freely.
- Rate-limited hosted APIs (NIM ~40 RPM, AF Server 30/day) are gated by **Redis token buckets** shared across all workers.

---

## 4. Data Model (Supabase / Postgres)

### 4.1 Core tables

```sql
-- Users handled by Supabase Auth (auth.users). App-level profile:
create table profiles (
  id          uuid primary key references auth.users(id),
  email       text not null,
  org         text,
  created_at  timestamptz default now()
);

-- A project groups runs (e.g., "IPF program")
create table projects (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references profiles(id),
  name        text not null,
  created_at  timestamptz default now()
);

-- A run = one disease-to-candidate execution
create table runs (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id),
  owner_id        uuid not null references profiles(id),
  disease_name    text not null,
  efo_id          text,
  config          jsonb not null,         -- full RunConfig (section 5)
  status          text not null default 'pending',  -- pending|running|paused|completed|failed|aborted
  current_phase   int not null default 0,
  intent_mode     text not null,          -- explore|repurpose|de_novo
  dry_run         boolean not null default false,
  cost_estimate   numeric,                -- USD, from dry_run
  cost_actual     numeric default 0,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

-- One row per phase per run = the resume checkpoint + output pointer
create table phase_results (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  phase           int not null,           -- 0..9
  status          text not null default 'pending', -- pending|running|completed|failed|skipped
  input_json      jsonb,                  -- I/O contract input
  output_json     jsonb,                  -- I/O contract output (the JSON the next phase consumes)
  artifact_paths  text[],                 -- Supabase Storage keys (PDBs, trajectories, etc.)
  started_at      timestamptz,
  finished_at     timestamptz,
  error           text,
  unique(run_id, phase)
);

-- Every per-target object (target, candidate, pose) — queryable, not just blobs
create table targets (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  rank            int,
  ensembl_id      text,
  symbol          text,
  aggregate_score numeric,
  validation_score numeric,
  tdl             text,
  modality_primary text,
  modality_secondary text,
  evidence_trail  jsonb,
  created_at      timestamptz default now()
);

create table candidates (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  target_id       uuid references targets(id) on delete cascade,
  kind            text not null,          -- repurposing|de_novo_sm|biologic|peptide
  identifier      text,                   -- drug name / design id
  smiles          text,                   -- null for biologics
  sequence        text,                   -- null for small molecules
  combined_score  numeric,
  subscores       jsonb,
  artifact_paths  text[],
  created_at      timestamptz default now()
);

-- Decision audit log: every LLM gate decision, for reproducibility + review
create table decisions (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  phase           int not null,
  gate            text not null,          -- e.g. "1.1_efo_disambiguation"
  llm_provider    text not null,          -- anthropic|openai|lmstudio
  llm_model       text not null,          -- "claude-sonnet-4-6" / "gpt-4o" / "qwen/qwen3-4b-thinking-2507"
  prompt          text,
  raw_response    text,
  decision_json   jsonb,
  human_override  jsonb,                  -- non-null if a user overrode the gate in the UI
  created_at      timestamptz default now()
);

-- Per-step compute accounting (mirrors compute_log.json)
create table compute_log (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  phase           int,
  step            text,                   -- "4.3_diffdock"
  service         text,                   -- local|NIM|Neurosnap|Modal|RunPod|LMStudio
  cost_usd        numeric default 0,
  wall_time_s     numeric,
  created_at      timestamptz default now()
);

-- Map-reduce intermediate chunks (the resume point for literature etc.)
create table llm_chunks (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  task            text not null,          -- "phase1_literature_extraction"
  chunk_index     int not null,
  total_chunks    int not null,
  input_ref       text,                   -- e.g. PMID batch
  output_json     jsonb,                  -- extracted result for this chunk
  status          text not null default 'pending', -- pending|done|failed
  created_at      timestamptz default now(),
  unique(run_id, task, chunk_index)
);
```

### 4.2 Row-Level Security (multi-tenant isolation)
- Enable RLS on `projects`, `runs`, `phase_results`, `targets`, `candidates`, `decisions`, `compute_log`, `llm_chunks`.
- Policy: a row is visible/writable only if its `owner_id = auth.uid()` (or the user is a member of the owning project — see `project_members` if team sharing is added later).
- Workers use the **service role key** (bypasses RLS) but always scope queries by `run_id`.

### 4.3 Artifact storage
- Large binary artifacts (PDB, CIF, trajectories, ADMET CSVs) go to **Supabase Storage** bucket `runs/{run_id}/...`.
- `phase_results.artifact_paths` and `candidates.artifact_paths` hold the storage keys.
- The final Phase 9 package (the `output/` tree) is zipped and uploaded as `runs/{run_id}/package.zip`.

---

## 5. Run Configuration Schema (the input contract)

This is the single object the UI builds and the API validates. It **extends** the `Human Pipeline.md` Phase 0 inputs with intent mode, seed inputs, constraints, and run control.

```jsonc
{
  // ---- Disease (Phase 0.1) ----
  "disease_name": "idiopathic pulmonary fibrosis",   // required, free text
  "disease_efo_id": null,                            // optional, skips normalization if set
  "disease_mondo_id": null,
  "disease_doid_id": null,
  "icd10": null,

  // ---- Intent mode (NEW) ----
  // Controls which branches run. Avoids paying full compute for branches you don't want.
  "intent_mode": "explore",   // "explore" | "repurpose" | "de_novo"
  //   explore   -> Phases 1-9 full (repurposing + de novo per modality)
  //   repurpose -> Phases 1-4 + 8-9 only (skip de novo design Phases 5/6)
  //   de_novo   -> Phases 1-3 + 5/6 + 7-9 (skip repurposing Phase 4)

  // ---- Seed inputs (NEW) ----
  "seed_targets": ["TGFB1", "IL11"],   // force-include past Phase 1/2 thresholds
  "seed_smiles": [],                   // scaffolds to optimize; if set, Phase 5.2 de novo gen is skipped, goes straight to opt
  "exclude_targets": ["MUC5B"],        // prune known dead-ends, never scored/validated
  "exclude_drugs": ["simtuzumab"],     // prune from repurposing/results

  // ---- Constraint preferences (NEW) ----
  "tissue_of_interest": "Lung",        // correct GTEx/HPA tissue for expression & safety (Phase 2.7)
  "indication_type": "chronic",        // "chronic" | "acute" | "oncology" — shifts safety weight thresholds
  "selectivity_target": "TGFBR2",      // gene to actively AVOID hitting (off-target penalty in ADMET/Phase 8)
  "novelty_mode": false,
  // true → Phase 1 step 1.2b auto-excludes targets with approved drugs for this specific
  // indication (clinical_stage="approved"); boosts novelty weight 10%→35%, drops
  // ot_assoc 30%→12%. Recommended when running well-studied diseases (NSCLC, breast
  // cancer) to surface whitespace targets rather than repeating known biology.

  // ---- Auxiliary inputs (Phase 0.2) ----
  "patient_cohort": {
    "expression_matrix": null,         // storage key to genes x samples TSV
    "metadata": null,
    "vcf": null
  },
  "modality_preference": "any",        // small_molecule | biologic | peptide | any

  // ---- Budgets & caps (Phase 0.2) ----
  "budget_hosted_usd": 25,
  "target_count_max": 20,
  "candidates_per_target_max": 10,
  "repurposing_enabled": true,         // derived from intent_mode but overridable
  "de_novo_enabled": true,

  // ---- Run control (NEW) ----
  "resume_from_phase": null,           // int 0-9; resume an existing run from this phase
  "dry_run": false,                    // validate creds + estimate cost, run NO real compute
  "output_dir": "output/ipf_run",      // logical name; physical path derived per run_id

  // ---- LLM config (PLUGGABLE PER-USER — see PRD_llm_provider_layer.md) ----
  // User picks the backend per run. Pipeline reads provider capabilities and
  // adapts strategy (frontier -> single-pass synthesis; local -> tree-merge).
  "llm": {
    "provider": "lmstudio",            // "anthropic" | "openai" | "lmstudio"
    "anthropic": { "api_key_ref": "secret://user/anthropic", "model": "claude-sonnet-4-6" },
    "openai":    { "api_key_ref": "secret://user/openai",    "model": "gpt-4o" },
    "lmstudio":  { "base_url": "http://localhost:1234/v1",
                   "model": "qwen/qwen3-4b-thinking-2507" },
    "temperature": 0.1,
    "self_consistency_override": null, // null = auto by quality_tier
    "llm_budget_usd": null             // optional cap on LLM token spend (cloud)
  }
}
```

> **LLM backend is user-selectable per run** (Anthropic / OpenAI / local LM Studio). See **`PRD_llm_provider_layer.md`** for the provider interface, capability-driven strategy adaptation, secrets handling, and credential schema. The pipeline calls one provider-agnostic interface; no phase imports a vendor SDK directly.

### 5.1 Intent-mode → phase routing table

| intent_mode | P0 | P1 | P2 | P3 | P4 (repurp) | P5 (SM) | P6 (bio) | P7 | P8 | P9 |
|---|---|---|---|---|---|---|---|---|---|---|
| `explore` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓* | ✓* | ✓ | ✓ | ✓ |
| `repurpose` | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ |
| `de_novo` | ✓ | ✓ | ✓ | ✓ | ✗ | ✓* | ✓* | ✓ | ✓ | ✓ |

`*` P5 vs P6 chosen per-target by the Phase 3 modality gate. `seed_smiles` set → P5.2 generation skipped, optimization-only.

### 5.2 Seed input semantics

| Field | Effect | Phase touched |
|---|---|---|
| `seed_targets` | Bypass association/validation cutoffs; always carried into P3+ (flagged `seeded=true`) | 1.2, 1.8, 2.9 |
| `seed_smiles` | Inject as starting molecules; skip de novo generation, go to filter/opt | 5.2 → 5.3 |
| `exclude_targets` | Removed before any scoring; never appears in output | 1.2 |
| `exclude_drugs` | Removed from repurposing library + final results | 4.1, 9 |
| `selectivity_target` | Added as anti-target; off-target hit = penalty | 5.4, 8.2 |
| `tissue_of_interest` | Default tissue for expression/safety queries | 2.7 |
| `indication_type` | Adjusts safety thresholds (oncology tolerates more tox; chronic least) | 2.1, 5.4, 8.3 |
| `novelty_mode` | Auto-excludes approved-for-this-indication targets; re-weights novelty 10%→35%; LLM advisory gate fires when >50% of top-20 are clinically addressed | 1.2b, 1.8 |

---

## 6. The Map-Reduce-then-Synthesize Pattern (platform-wide, capability-driven)

This is a **core, reusable platform primitive**, not a one-off. It applies anywhere the LLM must reason over more content than fits comfortably in the active provider's context (literature, large hit lists, multi-target summaries, ADMET batches). The **REDUCE strategy adapts to the chosen LLM provider's capabilities** (`PRD_llm_provider_layer.md`): a small local model uses hierarchical tree-merge; a frontier large-context model (Claude/OpenAI) synthesizes in a single pass.

### 6.1 Pattern

```
BIG TASK (N items)
   │
   ├─ split into chunks sized to provider.context_tokens
   │     (8 items/chunk local … up to ~80/chunk frontier)
   │
   ├─ MAP:  for each chunk i:   (identical across providers)
   │          - provider.complete(prompt, schema=...) → structured JSON
   │          - (local only) strip <think>...</think>
   │          - validate against Pydantic schema
   │          - persist to llm_chunks(run_id, task, chunk_index, output_json)
   │          - (resume point: skip chunks already status='done')
   │
   ├─ REDUCE:  strategy chosen from provider.capabilities
   │     • small local  -> hierarchical tree-merge (groups of ~8, repeat)
   │     • frontier      -> single-pass synthesis over all chunk outputs
   │
   └─ FINAL: write synthesized output to phase_results.output_json
```

### 6.2 Why the strategy adapts to the provider
A 4B local model cannot hold 500 extracted records at once, so for local we **tree-merge**:
- Round 1: merge chunks in groups of ~8 → e.g., 500 chunks → ~63 partial summaries.
- Round 2: merge those in groups of 8 → ~8 summaries.
- Round 3: merge to 1 final ranked, deduplicated result.

A frontier model (Claude 200k, OpenAI 128k) **skips the tree** — it ingests all chunk outputs in one synthesis call, which is simpler and higher quality. The map phase is identical and resumable in both cases; only the reduce step differs. Each merge/synthesis prompt asks the model to **deduplicate, aggregate scores, and keep the strongest evidence** per entity.

### 6.3 Reusable interface (spec)

```python
# src/llm/mapreduce.py  (spec — built later)
def map_reduce(
    run_id: str,
    task: str,                      # "phase1_literature_extraction"
    items: list,                    # raw items (abstracts, hits, ...)
    chunk_size: int,
    map_prompt_fn: Callable,        # (chunk) -> prompt
    map_schema: BaseModel,          # Pydantic schema for one chunk's output
    reduce_prompt_fn: Callable,     # (list_of_partials) -> prompt
    reduce_schema: BaseModel,
    reduce_fanin: int = 8,
) -> dict: ...
```

### 6.4 Resume guarantee
Because every chunk's output is persisted to `llm_chunks` keyed by `(run_id, task, chunk_index)`, a crash at chunk 47 of 500 resumes at 47. The reduce tree is recomputed from persisted chunk outputs (cheap, deterministic at temp=0.1).

---

## 7. Concurrency, Rate Limits & GPU Contention

### 7.1 Celery queues

| Queue | Worker type | Concurrency | Phases/steps routed here |
|---|---|---|---|
| `cpu` | CPU workers (scale to cores) | high | DB pulls, NetworkX, RDKit filters, scoring, packaging |
| `gpu` | GPU worker | **1** | local MD (GROMACS/OpenMM), REINVENT4, ProteinMPNN, local Boltz |
| `llm` | LLM worker | 1–2 local / higher for cloud | all LLM calls via the provider interface. Local LM Studio = single model server (concurrency 1–2); cloud providers (Anthropic/OpenAI) can run higher concurrency, bounded by their own rate limits + `llm_budget_usd` |
| `hosted` | I/O workers | medium | NIM, Neurosnap, AF Server, Modal, RunPod, ADMETlab calls |

### 7.2 Shared rate-limit buckets (Redis)
- `nim_rpm` token bucket: refill 40/min, shared across all `hosted` workers.
- `afserver_daily` bucket: 30/day, persisted; when exhausted → phase parks task and reschedules next day (per spec failure mode).
- `clue_daily`, `disgenet_daily`, `omim_daily` similarly.
- A worker `acquire(bucket)` blocks (with backoff) until a token is free.

### 7.3 GPU contention
- Local 6 GB GPU is a singleton resource → only the `gpu` queue touches it, concurrency=1.
- LM Studio also uses the GPU. **Decision:** run LM Studio on the GPU but treat the `llm` and `gpu` queues as mutually exclusive via a Redis lock `gpu_lock` when a `gpu`-queue MD job needs full VRAM, OR (recommended for the 6 GB box) run LM Studio model fully in VRAM persistently and route heavy MD to RunPod when local VRAM is contended. Documented as a deployment toggle `GPU_SHARING_MODE = exclusive | lmstudio_resident`.

---

## 8. Gradio UI (functional spec)

### 8.1 Screens
1. **New Run** — form that builds the RunConfig (Section 5). Includes intent mode selector, seed/exclude inputs, constraint fields, budget, and a **"Dry Run (estimate cost)"** button.
2. **Run Dashboard** — live phase progress (0→9), per-phase status badges, cost-so-far vs budget, current decision-gate log.
3. **Gate Review (optional human-in-loop)** — when a gate is flagged low-confidence by the LLM, surface the decision + reasoning and allow **human override** (written to `decisions.human_override`). Configurable: auto-proceed vs pause-for-review per gate.
4. **Results** — ranked targets table, per-target candidate tables, 3D pose viewer (NGL/py3Dmol embed), evidence trails, download `package.zip`.
5. **Runs List** — all runs for the user/project, status, cost, resume button.

### 8.2 Live progress mechanism
- Gradio polls `GET /runs/{id}` (or uses a generator with `yield` for streaming) reading `phase_results` + `compute_log`.
- UI never blocks on the pipeline — the pipeline runs in Celery workers; the UI is a thin client over the API.

### 8.3 Dry run UX
`dry_run=true` → API/worker validates all configured credentials (Phase 0.4 health checks), estimates per-phase cost from the Compute Budget Table, and returns `{credentials_ok, missing[], cost_estimate_usd, phase_breakdown[]}` **without running real compute**. UI shows a go/no-go summary.

---

## 9. Resume & Failure Semantics

### 9.1 Resume
- `resume_from_phase=K` (or "Resume" button on a failed run): worker loads `phase_results` for phases `< K` (must be `completed`), reconstructs the input contract for phase K from phase K-1's `output_json`, and continues.
- Within a phase, the map-reduce `llm_chunks` table provides sub-phase resume.

### 9.2 Failure modes (from Human Pipeline.md, made programmatic)

| Failure | Detection | Automated recovery |
|---|---|---|
| No EFO match | Phase 1.1 returns score < 0.6 | LLM tries MONDO/OMIM; else mark run `failed` w/ diagnostic |
| OT returns 0 targets | empty associatedTargets | fall back to literature(1.4)+GWAS(1.5) as primary |
| NIM throttled | 429 / bucket empty | reroute `hosted` task to Neurosnap → HuggingFace → defer |
| AF Server 30/day hit | bucket empty | ESMFold via NIM for non-complex; park AF3 task to next day |
| pLDDT < 70 throughout | Phase 2.2 output | route to 2.6 disordered subroutine |
| All pockets undruggable | Phase 2.3 | disable SM branch, force biologic/PROTAC |
| MD diverges on RTX 3050 | RMSD > 3Å sustained | reduce timestep / shorten / burst to RunPod A100 |
| Zero final candidates | Phase 8/9 | loop back to P5/6 with relaxed thresholds (max 2 outer iterations) |

### 9.3 Iteration policy
At most **2 outer iterations** (relax thresholds → re-run from 1.8 or 2.9). After 2 failures, output "no tractable candidates + failure modes" (per spec).

---

## 10. Configuration & Secrets

- `.env` (never committed) holds: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`, `REDIS_URL`, `LMSTUDIO_BASE_URL`, `NIM_API_KEY`, `NEUROSNAP_API_KEY`, `MODAL_TOKEN`, `RUNPOD_API_KEY`, `CLUE_API_KEY`, `OMIM_API_KEY`, `NCBI_API_KEY`, `GPU_SHARING_MODE`.
- `config.yaml` (committed) holds: scoring weights per `indication_type`, chunk sizes, rate-limit values, queue routing, model name.
- All DB version pins (OT release, ChEMBL version, AFDB v4, PrimeKG release) recorded per run in `runs.config` + `run_metadata.json`.

---

## 11. Tech Stack Summary

| Layer | Choice |
|---|---|
| UI | Gradio (Blocks) + py3Dmol/NGL viewer |
| API | FastAPI + Pydantic v2 |
| Queue | Celery + Redis |
| DB / Storage / Auth | Supabase (Postgres 15, Storage, Auth, RLS) |
| LLM (pluggable) | Provider interface over Anthropic (`anthropic`), OpenAI (`openai`), and local LM Studio (OpenAI-compatible, `qwen/qwen3-4b-thinking-2507`); see `PRD_llm_provider_layer.md` |
| Local sci tools | conda env `rxdis` (Python **3.10**) — RDKit, OpenMM, GROMACS, Vina, fpocket, REINVENT4, ProteinMPNN, gmx_MMPBSA, NetworkX, decoupleR, BoTorch |
| Hosted clients | httpx + requests-cache + ratelimit |
| Packaging | Docker + docker-compose (api, worker-cpu, worker-gpu, worker-llm, redis) |

> **Python version warning:** the current `.venv` is Python **3.14**, which cannot build RDKit/OpenMM/many sci packages today. The scientific worker MUST run in a **conda env on Python 3.10**. The FastAPI/Gradio/Celery web layer can run on 3.11+, but to avoid split environments, the PRDs assume **3.10 everywhere**. See `requirements.txt` header.

---

## 12. Milestones (maps to Human Pipeline.md staged build order)

| Milestone | Scope | Acceptance |
|---|---|---|
| M0 | Infra: Supabase schema, Redis, Celery, LM Studio client, Gradio shell, `dry_run` | Submit a run, see it queued, dry_run returns cost estimate |
| M1 | Phase 0 + Phase 1 | "pancreatic cancer" → top-20 with KRAS/TP53/CDKN2A/SMAD4 in top 10; with `novelty_mode=True`: KRAS/EGFR rank ≥5 positions lower, ≥3 Tbio/Tdark targets enter top 10 |
| M2 | Phase 2 + 3 | KRAS G12C → cryptic switch-II pocket, recommends covalent SM |
| M3 | Phase 4 | reproduce known approved-drug pairs for ≥3 targets |
| M4 | Phase 5 | ≥1 generated molecule Tanimoto >0.6 to a known approved drug |
| M5 | Phase 6 | ipTM >0.7 on PD-L1 benchmark |
| M6 | Phase 7 + 8 | binding-ranking reproducible across two runs |
| M7 | Phase 9 + reproducibility | full package.zip, pinned versions, Dockerfile |

---

## 13. Success Criteria (platform-level)

1. **Concurrency:** ≥5 runs execute concurrently without state corruption (RLS-isolated).
2. **Resumability:** kill a worker mid-Phase-5; resume completes the run with no recomputation of completed phases.
3. **Cost control:** `dry_run` estimate within ±30% of actual spend on the IPF worked example.
4. **Local-LLM gates:** every human gate in `Human Pipeline.md` has an automated LLM decision logged in `decisions`.
5. **Reproducibility:** two runs of the same disease + config + pinned DBs produce the same ranked target top-10 (decisions at temp=0.1).
6. **Offline reasoning:** with the `lmstudio` provider selected and hosted compute mocked, the full reasoning/decision layer runs with no external API calls. With `anthropic`/`openai` selected, the same pipeline runs with capability-adapted strategy and LLM cost accounted in `compute_log`.
7. **Provider portability:** the same disease + config produces a valid Phase 9 package regardless of which LLM provider is selected; no phase module imports a vendor SDK directly (only the provider interface).

---

## 14. Open Risks

| Risk | Mitigation |
|---|---|
| 6 GB GPU shared between LM Studio + MD | `GPU_SHARING_MODE` toggle; burst MD to RunPod |
| Local 4B synthesis quality < cloud | hierarchical reduce + strict schemas + 2× self-consistency on critical gates |
| Hosted API deprecation | Phase 0 health checks re-run per disease run; auto-reroute table |
| Python 3.14 venv incompatibility | mandate conda 3.10 for sci worker (Section 11) |
| Long runs (~36h) hit Celery visibility timeout | set `visibility_timeout` high; phase-level checkpointing makes restarts cheap |
| ChEMBL indication mapping coverage | EFO→ChEMBL disease linkage is ~80% complete; rare diseases and non-English indication names may miss active clinical programs, causing `indication_novelty` to be over-optimistic. Mitigation: fallback to MeSH ID + disease name fuzzy match in step 1.2b; log `coverage_confidence` in the target's `evidence_trail`. |
