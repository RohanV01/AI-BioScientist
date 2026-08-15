# LLD-01: Phase 0 — System Setup & Health Checks

**Source:** `src/phases/phase0/`  
**PRD:** `docs/PRD_phase0_setup.md`  
**Celery queue:** `cpu`  
**Input:** `RunConfig`  
**Output:** `phase0_output: dict` → stored in `phase_results.output_json` (phase=0)

---

## 1. Module Structure

```
src/phases/phase0/
├── __init__.py
├── checks.py     — individual check functions
└── runner.py     — orchestrates all checks, writes DB
```

---

## 2. Entry Point

```python
# src/phases/phase0/runner.py

def run_phase0(
    run_id: str,
    config: RunConfig,
    db,                    # Supabase service client
) -> dict:
    """
    Returns the phase0 output dict.
    Writes phase_results row (phase=0) to DB.
    Raises RuntimeError if DB unavailable.
    """
```

### Execution sequence inside `run_phase0`

1. `_mark_running(db, run_id)` — upsert `phase_results(phase=0, status="running", started_at=now)`
2. Call `run_all_checks(config)` → `CheckResult` object
3. Invoke LLM gate `0.dryrun_summary` if `config.dry_run` or any blockers found
4. Write `phase_results(phase=0, status, output_json, finished_at)`
5. Return output dict

---

## 3. `checks.py` — Individual Check Functions

### 3.1 Credential checks

```python
def check_llm_provider(config: RunConfig) -> CheckEntry:
    """
    Probes the configured LLM provider with a minimal request.
    - anthropic: POST messages, 1 token → checks HTTP 200
    - openai: GET /models or 1-token completion
    - lmstudio: GET {base_url}/v1/models → checks model id match
    Returns: CheckEntry(service, ok, latency_ms, detail)
    """

def check_supabase(config: RunConfig) -> CheckEntry:
    """SELECT 1 FROM runs using SUPABASE_SERVICE_KEY."""

def check_optional_api(service: str, env_var: str, probe_url: str) -> CheckEntry:
    """
    Generic probe for NIM, Neurosnap, CLUE, OMIM, NCBI, Modal, RunPod.
    Skips if env_var not set. Returns ok=False with detail='not_configured' if absent.
    """
```

### 3.2 Database presence checks

```python
def check_local_databases(config: RunConfig) -> List[CheckEntry]:
    """
    For each required DB (intent_mode-aware):
      1. Check file exists at expected path (from settings.*).
      2. Extract version string (file header, first line, or checksum if no header).
      3. Record in CheckEntry.version field.
    Returns list of CheckEntry per DB.

    Required by intent_mode:
      always: STRING, DepMap, GTEx, AlphaMissense, ChEMBL, PrimeKG
      de_novo only: HGNC gene map (built from STRING ENSP headers)
    """
```

### 3.3 Endpoint deprecation check

```python
def check_hosted_endpoints() -> List[EndpointEntry]:
    """
    Probes each NIM / Neurosnap model endpoint.
    Models checked: alphafold2-nim, diffdock-nim, rfdiffusion-nim,
                    proteinmpnn-nim, genmol-nim, boltz-2-neurosnap.
    Returns: List[EndpointEntry(model, live, deprecated, fallback)]
    Builds reroute_table: Dict[str, str] mapping deprecated/down models
    to their fallback alternatives.
    """
```

### 3.4 GPU / VRAM probe

```python
def probe_gpu() -> GPUInfo:
    """
    Uses torch.cuda if available, else falls back to nvidia-smi subprocess.
    Returns: GPUInfo(name, vram_total_gb, vram_free_gb, sharing_mode)

    sharing_mode logic:
      - vram_free_gb < 3 → "lmstudio_resident" (warn: may need to close LM Studio for MD)
      - 3 ≤ vram_free_gb < 8 → "shared"
      - vram_free_gb ≥ 8 → "dedicated"
    """
```

### 3.5 Cost estimation

```python
def estimate_cost(config: RunConfig) -> float:
    """
    Uses the Compute Budget Table from the PRD:
      Phase 4: ~$1 NIM + Boltz-2 per target
      Phase 5: ~$3 RunPod (library docking) + ~$1 NIM per target
      Phase 6: ~$2 Neurosnap BoltzGen per target
      Phase 8: ~$1.40 RunPod MD per candidate, ~$2-5 Modal FEP per pair
    Multiplied by target_count_max and candidates_per_target_max.
    Returns estimated total USD.
    """
```

---

## 4. `CheckResult` and `CheckEntry` types

```python
@dataclass
class CheckEntry:
    service: str
    ok: bool
    latency_ms: float
    detail: str
    version: Optional[str] = None

@dataclass
class EndpointEntry:
    model: str
    live: bool
    deprecated: bool
    fallback: Optional[str] = None

@dataclass
class GPUInfo:
    name: str
    vram_total_gb: float
    vram_free_gb: float
    sharing_mode: str   # "lmstudio_resident" | "shared" | "dedicated" | "none"

@dataclass
class CheckResult:
    credentials: List[CheckEntry]
    databases: List[CheckEntry]
    endpoints: List[EndpointEntry]
    reroute_table: Dict[str, str]
    gpu: GPUInfo
    cost_estimate_usd: float
    missing_required: List[str]
    go_no_go: str   # "go" | "fix_first" | "no_go"
```

---

## 5. `go_no_go` Logic

```python
def compute_go_no_go(result: CheckResult, config: RunConfig) -> str:
    """
    no_go   → any required credential check failed AND it is required for this intent_mode
    no_go   → LLM provider check failed (always required)
    no_go   → Supabase check failed
    fix_first → any required DB missing
    fix_first → GPU sharing_mode == "lmstudio_resident" AND Phase 8 MD planned
    go      → all required checks pass
    """
```

---

## 6. LLM Gate: `0.dryrun_summary`

**When:** Always (dry_run=True), or when any blockers found.

**Prompt structure:**
```
Given these health check results: {credentials_summary}
Missing required: {missing_required}
Cost estimate: ${cost_estimate_usd}
GPU: {gpu.name}, {gpu.vram_free_gb} GB free

Write a plain-English go/no-go recommendation for a computational chemist.
List blockers clearly. Rate urgency of warnings.

Return JSON: {
  "recommendation": "go" | "fix_first" | "no_go",
  "blockers": [...],
  "warnings": [...],
  "summary": "..."
}
```

**Fallback (LLM off):** Return `{recommendation: go_no_go, blockers: missing_required, warnings: [], summary: "Auto-generated"}`.

**Stored in:** `decisions` table (phase=0, gate="0.dryrun_summary").

---

## 7. Output JSON Contract

```json
{
  "credentials": [
    {"service": "lmstudio", "ok": true, "latency_ms": 12, "detail": "model qwen3-4b ready"},
    {"service": "supabase", "ok": true, "latency_ms": 45, "detail": ""}
  ],
  "databases": [
    {"name": "STRING", "present": true, "version": "v12.0", "path": "Databases/string/..."},
    {"name": "DepMap", "present": true, "version": "Q4_2024"}
  ],
  "endpoints": [
    {"model": "diffdock-nim", "live": true, "deprecated": false},
    {"model": "genmol-nim", "live": false, "deprecated": true, "fallback": "reinvent4"}
  ],
  "reroute_table": {"genmol-nim": "reinvent4"},
  "gpu": {"name": "RTX 3050", "vram_free_gb": 2.3, "sharing_mode": "lmstudio_resident"},
  "cost_estimate_usd": 38.5,
  "missing_required": [],
  "go_no_go": "go",
  "summary": "All systems ready. GPU has 2.3 GB free — recommend RunPod for MD in Phase 8."
}
```

---

## 8. Failure / Recovery

| Failure | Behaviour |
|---|---|
| LM Studio not running | `go_no_go = "no_go"`, `missing_required = ["lmstudio"]` |
| Supabase down | `go_no_go = "no_go"` — hard block, no DB = no run |
| Required DB file missing | `go_no_go = "fix_first"`, named in `missing_required` |
| Optional API key absent | `ok=False, detail="not_configured"` — warning only, not blocker |
| GPU probe fails (no CUDA, no nvidia-smi) | `GPUInfo(name="none", vram_free_gb=0, sharing_mode="none")` |
| LLM gate errors | Fallback to deterministic `go_no_go` value |

---

## 9. DB Writes

```
phase_results: phase=0, status=running → completed/failed
               input_json = {run_id, intent_mode, dry_run}
               output_json = <full output dict above>
decisions:     phase=0, gate="0.dryrun_summary" (if LLM ran)
compute_log:   phase=0, step="credential_probes", service="supabase/lmstudio/..."
               wall_time_s = total check time
```
