# LLD-00: System Architecture

**Document type:** Low-Level Design  
**Version:** 1.0 (2026-06-07)  
**Scope:** End-to-end platform architecture — processes, threads, data flow, external integrations

---

## 1. Process Topology

```
┌─────────────────────────────────────────────────────────────────┐
│  User (browser)                                                  │
│  React 19 + Vite 6, port 5173                                   │
│  Zustand store ← WebSocket / REST ← FastAPI                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/WS
┌───────────────────────────▼─────────────────────────────────────┐
│  FastAPI + Uvicorn, port 8000                                    │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────────┐ │
│  │  REST routes │  │  WS /stream    │  │  EventHub registry   │ │
│  │  (main.py)   │  │  (main.py)     │  │  (events.py)         │ │
│  └──────────────┘  └────────────────┘  └──────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Orchestrator (orchestrator.py)                            │  │
│  │  Celery chain path     |  Thread fallback path             │  │
│  │  (when Redis present)  |  (sequential daemon thread)       │  │
│  └────────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
            ┌───────────────┴──────────────────┐
            │                                  │
┌───────────▼──────────────┐   ┌───────────────▼──────────────────┐
│  Celery Workers          │   │  Supabase (PostgreSQL)            │
│  (workers/tasks.py)      │   │  Tables: runs, phase_results,     │
│  queues: cpu/gpu/hosted  │   │  targets, candidates, decisions,  │
│  └─ Phase runners        │   │  compute_log, llm_chunks,         │
│     P0 → P9              │   │  user_llm_credentials, profiles,  │
└──────────────────────────┘   │  projects                         │
                               └──────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────┐
│  Local Databases  (flat files, read-only)                        │
│  STRING   Databases/string/9606.protein.links.detailed.v12.0.txt │
│  DepMap   Databases/depmap/CRISPRGeneEffect.csv                  │
│  GTEx     Databases/gtex/*_gene_tpm.parquet                      │
│  AlphaMissense Databases/alphamissense/AlphaMissense_hg38.tsv    │
│  ChEMBL   Databases/chembl/chembl_35.db (SQLite)                 │
│  PrimeKG  Databases/primekg/{nodes.csv,edges.csv}                │
│  HGNC gene map (derived at runtime)                              │
└──────────────────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────┐
│  External APIs (hosted compute)                                  │
│  NVIDIA NIM (ESMFold, RFdiffusion, DiffDock-V2, ProteinMPNN)     │
│  Neurosnap (BoltzGen, Boltz-2, NetSolP, Aggrescan3D)             │
│  AlphaFold Server (AF3 complexes)                                │
│  CLUE.io (LINCS L1000 reverse signatures)                        │
│  RunPod (A100 burst MD / library docking)                        │
│  Modal (PMX relative FEP, ProteomeLM-Ess, PPI Docker)            │
│  Open Targets GraphQL (free)                                     │
│  UniProt REST / RCSB PDB REST / HPA REST / GTEx REST             │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Configuration Entry Point: `RunConfig`

`src/config/run_config.py` — Pydantic v2 model, validated at POST `/api/runs`.

| Field | Type | Default | Notes |
|---|---|---|---|
| `disease_name` | `str` | required | Free-text, used in EFO resolution |
| `disease_efo_id` | `str` | required | EFO_xxxxxxx — required since 2026-06-07 |
| `intent_mode` | `Literal["explore","repurpose","de_novo"]` | `"explore"` | Gates which phases run |
| `known_positives` | `List[str]` | `[]` | PU-learning anchor genes (5–10 for best quality) |
| `seed_targets` | `List[str]` | `[]` | Fallback positives if `known_positives` empty |
| `seed_smiles` | `List[str]` | `[]` | Forces SM optimization-only in P5 for those targets |
| `exclude_targets` | `List[str]` | `[]` | Never appear in output |
| `exclude_drugs` | `List[str]` | `[]` | Pruned from all candidate outputs |
| `tissue_of_interest` | `str` | `"Lung"` | GTEx tissue column for expression queries |
| `indication_type` | `Literal["chronic","acute","oncology"]` | `"chronic"` | Adjusts ADMET/scorecard thresholds |
| `selectivity_target` | `Optional[str]` | `None` | Anti-target for off-target penalty |
| `budget_hosted_usd` | `float` | `25.0` | MPO loop + hosted API budget cap |
| `target_count_max` | `int` | `20` | Max targets out of Phase 1 |
| `candidates_per_target_max` | `int` | `10` | Max candidates per target per kind |
| `repurposing_enabled` | `bool` | `True` | Auto-False when `intent_mode=de_novo` |
| `de_novo_enabled` | `bool` | `True` | Auto-False when `intent_mode=repurpose` |
| `resume_from_phase` | `Optional[int]` | `None` | Skip completed phases |
| `dry_run` | `bool` | `False` | Phase 0 only; zero hosted compute |
| `llm` | `LLMConfig` | lmstudio default | Provider + model selection |

### `LLMConfig` sub-model

```python
class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai", "lmstudio"] = "lmstudio"
    anthropic: Optional[LLMAnthropicConfig] = None   # api_key_ref, model
    openai: Optional[LLMOpenAIConfig] = None          # api_key_ref, model
    lmstudio: LLMLMStudioConfig = ...                 # base_url, model
    temperature: float = 0.1
    self_consistency_override: Optional[int] = None
    llm_budget_usd: Optional[float] = None
```

---

## 3. Orchestration: Two Execution Paths

### 3.1 Celery chain path (Redis present)

```
chain(
  run_phase0_task.si(run_id, cfg_dict),
  run_phase1_task.si(run_id, cfg_dict),
  run_phase2_task.si(run_id, cfg_dict),
  run_phase3_task.si(run_id, cfg_dict),
  chord(
    [run_phase4_task, run_phase5_task, run_phase6_task],   # parallel
    run_phase7_task.si(run_id, cfg_dict)                   # callback
  ),
  run_phase8_task.si(run_id, cfg_dict),
  run_phase9_task.si(run_id, cfg_dict)
)
```

A `_celery_monitor` daemon thread polls every 5 s for newly completed `phase_results` rows and emits EventHub events for the UI.

### 3.2 Thread fallback path (no Redis)

Sequential `threading.Thread` (`_thread_worker`). Same phase call sequence. Events emitted synchronously inside `capture_to_hub` context. Used in development.

### 3.3 `through_phase` parameter

Both paths accept `through_phase: int` (default = 1, max = `MAX_IMPLEMENTED_PHASE = 9`). When `through_phase < 4`, P4/P5/P6 are not dispatched. This is used by the module-run feature (single-phase launch from the UI).

---

## 4. Event System

`src/api/events.py` — `EventHub` is a per-run in-process event bus.

### `EventHub.emit(event_type, **payload)` — event types

| Type | Key fields | When emitted |
|---|---|---|
| `run` | `status: running/completed/failed`, `through_phase`, `executor` | Run lifecycle |
| `phase` | `phase: int`, `name: str`, `status: pending/running/completed/failed` | Each phase transition |
| `note` | `phase: int`, `title: str`, `data: dict` | Phase summary data |
| `targets_ready` | `phase: int` | After Phase 1 completes |
| `telemetry` | `cpu_pct, ram_used_gb, vram_used_gb, ...` | Periodic system metrics |
| `log` | `level, logger, message` | Python logging → WS |

### WebSocket stream protocol

`GET /api/runs/{id}/stream` — WebSocket. On connect:
1. Replay buffered events from `EventHub.replay_buffer`.
2. Tail new events as they arrive.
3. Send `{"type":"done"}` when hub is closed.

Polling fallback: `GET /api/runs/{id}/events` returns the replay buffer as a JSON array.

---

## 5. Database Layer

`src/db/run_state.py` — all DB writes go through this module (service-role client bypasses RLS).

### Key functions

```python
def upsert_phase_result(run_id, phase, status, input_json=None, output_json=None,
                        artifact_paths=None, error=None) -> None

def upsert_target(run_id, symbol, rank, ensembl_id, aggregate_score,
                  evidence_trail, tdl=None, seeded=False) -> None

def insert_candidate(run_id, target_id, kind, identifier=None, smiles=None,
                     sequence=None, combined_score=None, subscores=None,
                     artifact_paths=None) -> None

def insert_decision(run_id, phase, gate, llm_provider, llm_model, prompt,
                    raw_response, decision_json, human_override=None) -> None

def log_compute(run_id, phase, step, service, cost_usd=0.0, wall_time_s=None) -> None

def get_phase_output(run_id, phase) -> Optional[dict]
```

### `candidates.target_id` type note

`target_id` is `text` (gene symbol), NOT a UUID FK to `targets.id`. The pipeline keys candidates by symbol. The DB column is named `target_id` but holds values like `"KRAS"`.

---

## 6. LLM Provider Layer

`src/llm/` — abstract `LLMProvider` base class with three implementations.

```python
class LLMProvider(ABC):
    def complete(self, prompt: str, temperature: float = 0.1,
                 max_tokens: int = 4096) -> LLMResponse
    def complete_json(self, prompt: str, schema: dict,
                      temperature: float = 0.1) -> dict

class LMStudioProvider(LLMProvider): ...   # HTTP to localhost:1234/v1
class AnthropicProvider(LLMProvider): ...  # anthropic SDK
class OpenAIProvider(LLMProvider): ...     # openai SDK

def get_provider(llm_config: LLMConfig) -> LLMProvider  # factory
```

All phase runners receive the provider via DI (passed from orchestrator). LLM gates always have a deterministic fallback so the pipeline continues if the LLM is off.

---

## 7. Phase I/O Contract Summary

```
RunConfig
   │
   ▼ Phase 0
go_no_go, cost_estimate, credentials, databases, reroute_table
   │
   ▼ Phase 1
ranked_targets[{symbol, ensembl_id, aggregate_score, evidence_trail}], efo_id, model
   │
   ▼ Phase 2
validated_targets[{symbol, validation_score, structure, pockets, essentiality,
                   variants, safety, modality, shap, evidence_summary}]
   │
   ▼ Phase 3
routing[{symbol, primary, secondary, branches, repurposing_priority, modality_scores}]
   │
   ├──────────────────────────────────────────┐
   ▼ Phase 4                    ▼ Phase 5      ▼ Phase 6
repurposing{symbol:[candidates]}  de_novo_sm  biologic
   │                                │              │
   └────────────────────────────────┴──────────────┘
                                    │
                                    ▼ Phase 7
                        optimized{symbol: {pareto_front, hypervolume, iterations_run}}
                                    │
                                    ▼ Phase 8
                        validated candidates with combined_score, MD verdict, briefs
                                    │
                                    ▼ Phase 9
                        package.zip at Supabase Storage runs/{run_id}/package.zip
```

---

## 8. Settings (`src/config/settings.py`)

Environment variables read via `pydantic_settings.BaseSettings`:

| Var | Usage |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Service role key (bypasses RLS) |
| `SUPABASE_ANON_KEY` | Anon key (frontend auth) |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `DB_STRING` | Path to `Databases/string/` |
| `DB_DEPMAP` | Path to `Databases/depmap/` |
| `DB_GTEX` | Path to `Databases/gtex/` |
| `DB_ALPHAMISSENSE` | Path to `Databases/alphamissense/` |
| `DB_CHEMBL` | Path to `Databases/chembl/` |
| `DB_PRIMEKG` | Path to `Databases/primekg/` |
| `NIM_API_KEY` | NVIDIA NIM |
| `NEUROSNAP_API_KEY` | Neurosnap |
| `CLUE_API_KEY` | LINCS CLUE.io |
| `RUNPOD_API_KEY` | RunPod burst |
| `MODAL_TOKEN` | Modal.com |
| `RFDIFFUSION_DIR` | Path to local RFdiffusion clone |
| `P4_MAX_LIBRARY` | Docking library cap (default 3000) |
| `P4_WORKERS` | Vina parallel workers (default 4) |

---

## 9. Supabase Row-Level Security

Every user-owned table has `owner_id uuid` column. RLS policy: `using (owner_id = auth.uid())`. Service-role key bypasses RLS (used by backend workers). Frontend uses anon key + JWT for user-scoped reads. `phase_results`, `targets`, `candidates`, `decisions`, `compute_log` are scoped via `run_id → runs.owner_id`.

---

## 10. Artifact Storage

Large binary artifacts (PDB files, trajectory summaries, package.zip) are stored in Supabase Storage. Path convention:

```
runs/{run_id}/structure/{symbol}_pdb.pdb
runs/{run_id}/poses/{candidate_id}_pose.pdb
runs/{run_id}/poses/{candidate_id}_md_summary.json
runs/{run_id}/package.zip
```

`artifact_paths` column in `phase_results` and `candidates` stores the Storage keys.
