# PRD — Pluggable LLM Provider Layer

**Cross-cutting:** touches every phase (all decision gates + the map-reduce primitive)
**Maps to:** Master PRD §5 (RunConfig.llm), §6 (map-reduce), §4 (decisions/llm_chunks)
**Status:** supersedes the earlier "100% local, hard-set" LLM decision — now **user-selectable per run**

---

## Goal

Let each user choose, **per run**, which LLM backend powers all reasoning/synthesis:

- **Anthropic Claude** (API key) — highest quality, large context
- **OpenAI** (API key) — high quality, large context
- **Local LM Studio** (base URL) — free, offline, small context

The entire pipeline (every decision gate + the map-reduce literature/synthesis steps) calls **one provider-agnostic interface**. The pipeline reads the chosen provider's **capabilities** (context window, cost, quality tier) and **adapts its strategy automatically** — e.g., large-context cloud models skip hierarchical merge and synthesize in one pass; the small local model keeps the chunk → tree-merge pattern.

Users only configure what they have. If they supply only a local URL, cloud is unavailable for that run (and vice-versa).

---

## Inputs Required From You (the user, per run)

Exactly one of the following is required; more than one is allowed (then `provider` selects which is active):

| Provider | What the user inputs | Where it's stored |
|---|---|---|
| `anthropic` | API key (`sk-ant-...`), optional model id | encrypted in `user_llm_credentials` (or per-run secret) |
| `openai` | API key (`sk-...`), optional model id | encrypted |
| `lmstudio` | Base URL (default `http://localhost:1234/v1`), model id | per-run config (no secret) |

UI surfaces a connection test ("Verify") for each before the run starts (mirrors Phase 0.2 credential probe).

---

## Architecture

### The single interface every phase calls

```python
# src/llm/provider.py  (spec)

class LLMProvider(Protocol):
    name: str                         # "anthropic" | "openai" | "lmstudio"
    model: str
    capabilities: LLMCapabilities

    def complete(self, prompt: str, *, schema: BaseModel | None = None,
                 temperature: float = 0.1, max_tokens: int = 2048) -> LLMResult: ...

class LLMCapabilities(BaseModel):
    context_tokens: int               # 8k (local) … 200k (Claude) … 128k (OpenAI)
    supports_json_mode: bool          # native structured output
    cost_per_1k_input: float          # 0.0 for local
    cost_per_1k_output: float         # 0.0 for local
    quality_tier: str                 # "frontier" | "mid" | "small"
    strips_thinking_tags: bool        # local qwen-thinking emits <think>…</think>

class LLMResult(BaseModel):
    text: str
    parsed: dict | None               # validated against schema if provided
    input_tokens: int
    output_tokens: int
    cost_usd: float
```

### Three concrete adapters

| Adapter | SDK | Notes |
|---|---|---|
| `AnthropicProvider` | `anthropic` | uses tool-use / JSON for structured output; **prompt caching** for the long DB-context system prompts |
| `OpenAIProvider` | `openai` | `response_format=json_schema` for structured output |
| `LMStudioProvider` | `openai` (OpenAI-compatible) | base_url → LM Studio; strips `<think>…</think>`; cost = 0 |

All three are constructed by a **factory** from `RunConfig.llm`:

```python
def make_provider(cfg: LLMConfig) -> LLMProvider: ...
```

### The pipeline only ever imports the interface
No phase code references Claude/OpenAI/LM Studio directly. Every gate does:
```python
result = provider.complete(prompt, schema=GateSchema)
```
Swapping providers changes nothing in phase logic.

---

## Capability-Driven Strategy Adaptation (the important part)

The map-reduce primitive (Master PRD §6) **reads `provider.capabilities` and picks a strategy**:

| Capability | Strategy chosen | Why |
|---|---|---|
| `context_tokens < 16k` (local small) | **chunk + hierarchical tree-merge** | model can't hold all records; keep each call small |
| `context_tokens ≥ 100k` (Claude/OpenAI) | **larger chunks for extraction, single-pass reduce** | frontier model synthesizes 500 records in one call — better, simpler |
| `quality_tier == "small"` | **2× self-consistency on critical gates** (1.1, 2.3, 3, 8) | guard small-model variance |
| `quality_tier == "frontier"` | **single pass, no self-consistency** | trustworthy first answer |
| `cost_per_1k_output > 0` | **respect `budget_hosted_usd`**: count LLM cost toward budget; warn/stop | local is free, cloud is not |

```python
def map_reduce(run_id, task, items, map_prompt_fn, map_schema,
               reduce_prompt_fn, reduce_schema, provider):
    caps = provider.capabilities
    chunk_size = pick_chunk_size(caps.context_tokens)     # 8 local … 80 frontier
    reduce_mode = "single_pass" if caps.context_tokens >= 100_000 else "tree"
    # MAP: same for all providers (persist each chunk → llm_chunks, resumable)
    # REDUCE: tree-merge (local) OR one big synthesis call (frontier)
```

**Net effect:** a user with a Claude key gets a faster, higher-quality run that costs a few dollars in LLM tokens; a user with only LM Studio gets a free, fully-offline run using the chunked strategy. **Same pipeline, same outputs schema, adapted execution.**

---

## RunConfig.llm (updated — replaces Master PRD §5 "llm" block)

```jsonc
"llm": {
  "provider": "anthropic",            // "anthropic" | "openai" | "lmstudio"

  // present only for the selected provider (others omitted/null):
  "anthropic": { "api_key_ref": "secret://user/anthropic", "model": "claude-sonnet-4-6" },
  "openai":    { "api_key_ref": "secret://user/openai",    "model": "gpt-4o" },
  "lmstudio":  { "base_url": "http://localhost:1234/v1",
                 "model": "qwen/qwen3-4b-thinking-2507" },

  "temperature": 0.1,
  "self_consistency_override": null,  // null = auto by quality_tier; or force int N
  "llm_budget_usd": null              // optional cap specifically on LLM token spend
}
```

> `api_key_ref` is a pointer, never the raw key. Keys live encrypted (Section "Secrets").

---

## Data Model additions (extends Master PRD §4)

```sql
-- Per-user saved LLM credentials (encrypted at rest). Optional convenience;
-- a run can also carry an ephemeral key that is never persisted.
create table user_llm_credentials (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid not null references profiles(id),
  provider      text not null,        -- anthropic|openai|lmstudio
  enc_api_key   text,                 -- pgcrypto-encrypted; null for lmstudio
  base_url      text,                 -- lmstudio only
  default_model text,
  created_at    timestamptz default now(),
  unique(owner_id, provider)
);
```

`decisions` table already records `llm_model` per gate — extend usage to also store `llm_provider` (add column `llm_provider text`). This keeps the audit trail honest about *which* backend made each call.

`compute_log.service` already supports `LMStudio`; add `Anthropic` and `OpenAI` as values so LLM token cost is accounted per-step alongside hosted compute.

---

## Phase 0 impact (credential validation)

Phase 0.2 (PRD_phase0) gains an **LLM provider probe** for the selected provider:

| Provider | Probe |
|---|---|
| anthropic | minimal `messages` call (1 token) → confirm key + model live |
| openai | `GET /models` or 1-token completion |
| lmstudio | `GET /v1/models` → confirm model id matches |

Dry-run cost estimate now **includes projected LLM token cost** for cloud providers (0 for local), so the user sees total spend (hosted compute + LLM) before committing.

---

## UI impact (Master PRD §8)

**New Run form** gains an **LLM Backend** section:

```
── LLM Backend ──
( ) Anthropic Claude   API key [______________]  model [claude-sonnet-4-6 ▼]  [Verify]
( ) OpenAI             API key [______________]  model [gpt-4o            ▼]  [Verify]
(•) Local (LM Studio)  URL [http://localhost:1234/v1]  model [qwen3-4b-thinking ▼] [Verify]

ⓘ Cloud providers: faster, higher quality, costs ~$1–5 in tokens/run.
  Local: free & offline, uses chunked strategy (slightly slower).
```

- "Verify" runs the Phase 0.2 probe immediately and shows ✓/✗.
- Only providers the user configured are selectable.
- The dashboard shows which provider is active and LLM-token-cost-so-far.

---

## Secrets handling

- **Ephemeral (default):** key entered in the form is used for that run only, held in the worker's memory, never written to DB. Safest.
- **Saved (opt-in):** user clicks "save this key" → encrypted via Supabase `pgcrypto` into `user_llm_credentials`, decrypted only by the worker (service role) at run time.
- Never logged. `decisions.prompt`/`raw_response` are stored but keys never appear in prompts.
- `.env` `LLM_ENC_KEY` is the symmetric key for credential encryption.

---

## Success Criteria

1. A user with **only** an Anthropic key runs end-to-end; `decisions.llm_provider='anthropic'` for every gate; LLM token cost appears in `compute_log` and the dashboard.
2. A user with **only** LM Studio runs end-to-end fully offline; LLM cost = $0; map-reduce uses tree-merge.
3. Switching provider between two runs of the same disease changes **only** execution (speed/cost/strategy), and both produce a valid Phase 9 package with the same output schema.
4. Frontier provider auto-selects single-pass reduce; small local provider auto-selects tree-merge + 2× self-consistency on critical gates — verified in logs.
5. `dry_run` shows projected LLM token cost for cloud providers and $0 for local, included in the total estimate.
6. No phase module imports a provider SDK directly (only `src/llm/provider.py`).
7. Raw API keys never appear in DB rows, logs, or the `decisions` audit trail.

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| Selected provider key invalid | Phase 0 hard block; name the provider; offer to switch |
| Cloud provider rate-limited (429) | exponential backoff (tenacity); if persistent, offer fallback to a configured secondary provider or local |
| `llm_budget_usd` exhausted mid-run (cloud) | pause run, surface in UI, offer: raise budget / switch to local / abort |
| Local LM Studio server down mid-run | pause; prompt user to restart server; resume from last completed chunk/phase |
| Frontier model deprecated | Phase 0 health probe flags it; suggest current model id |
| Structured-output mismatch | provider-specific retry (Anthropic tool-use / OpenAI json_schema / local re-prompt + parse), then drop chunk to null (map-reduce tolerates) |
```
