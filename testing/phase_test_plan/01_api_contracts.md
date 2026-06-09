# API Contract Tests

All FastAPI endpoints, their expected request/response shapes, and Postman test assertions.
Run with the `/postman` skill — sync the OpenAPI spec, then execute this collection.

---

## Base URL

```
http://localhost:8000
```

Set as `{{base_url}}` in Postman environment.

---

## Endpoints

### 1. GET /api/health

**Purpose:** Liveness check + Supabase reachability.

**Request:** No body, no auth required.

**Expected response (200):**
```json
{
  "status": "ok",
  "supabase": true,
  "detail": "ok",
  "phases_implemented": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
}
```

**Postman assertions:**
```javascript
pm.test("Status 200", () => pm.response.to.have.status(200));
pm.test("Supabase reachable", () => pm.expect(pm.response.json().supabase).to.be.true);
pm.test("All 10 phases listed", () => pm.expect(pm.response.json().phases_implemented).to.have.lengthOf(10));
```

**Failure scenarios:**
- `supabase: false` → Supabase down or wrong keys
- `phases_implemented` missing phase 9 → orchestrator constant not updated

---

### 2. GET /api/system/telemetry

**Purpose:** Hardware snapshot (RAM, VRAM, CPU).

**Request:** Auth required (Bearer token).

**Expected response (200):**
```json
{
  "ram_used_gb": 12.4,
  "ram_total_gb": 32.0,
  "ram_pct": 38.7,
  "vram_used_mb": null,
  "vram_total_mb": null,
  "vram_pct": null,
  "cpu_pct": 22.1
}
```

**Postman assertions:**
```javascript
pm.test("Status 200", () => pm.response.to.have.status(200));
pm.test("RAM present", () => pm.expect(pm.response.json().ram_used_gb).to.be.a('number'));
pm.test("CPU present", () => pm.expect(pm.response.json().cpu_pct).to.be.a('number'));
```

---

### 3. GET /api/genes?q={symbol}

**Purpose:** Gene-symbol autocomplete for PU anchor search.

**Request:** `?q=KRAS&limit=10` — no auth required.

**Expected response (200):**
```json
{ "query": "KRAS", "results": ["KRAS", "KRAS2"] }
```

**Postman assertions:**
```javascript
pm.test("Status 200", () => pm.response.to.have.status(200));
pm.test("KRAS in results", () => pm.expect(pm.response.json().results).to.include('KRAS'));
pm.test("Results is array", () => pm.expect(pm.response.json().results).to.be.an('array'));
```

**Edge cases to test:**
- `?q=` (empty) → `results: []`
- `?q=ZZZNOTREAL` → `results: []`
- `?limit=1` → at most 1 result

---

### 4. GET /api/runs

**Purpose:** List all runs for current user.

**Request:** Auth required.

**Expected response (200):**
```json
{
  "runs": [
    {
      "id": "uuid",
      "disease_name": "pancreatic cancer",
      "status": "completed",
      "current_phase": 1,
      "intent_mode": "explore",
      "efo_id": "EFO_0002618",
      "cost_usd": null,
      "running": false,
      "created_at": "2026-06-06T..."
    }
  ],
  "phase_names": { "0": "Setup & Health", "1": "Target ID", ... }
}
```

**Postman assertions:**
```javascript
pm.test("Status 200", () => pm.response.to.have.status(200));
pm.test("Runs is array", () => pm.expect(pm.response.json().runs).to.be.an('array'));
pm.test("Phase names present", () => pm.expect(pm.response.json().phase_names).to.have.property('1'));
```

---

### 5. POST /api/runs

**Purpose:** Create and start a run.

**Request body:**
```json
{
  "disease": "pancreatic cancer",
  "disease_efo_id": "EFO_0002618",
  "known_positives": ["KRAS", "TP53", "SMAD4", "CDKN2A", "BRCA2"],
  "intent_mode": "explore",
  "tissue_of_interest": "Pancreas",
  "indication_type": "oncology",
  "provider": "lmstudio",
  "target_count_max": 20,
  "pu_n_bags": 30,
  "through_phase": 1
}
```

**Expected response (200):**
```json
{ "run_id": "uuid", "through_phase": 1 }
```

**Postman assertions:**
```javascript
pm.test("Status 200", () => pm.response.to.have.status(200));
pm.test("run_id present", () => pm.expect(pm.response.json().run_id).to.be.a('string'));
pm.test("through_phase echoed", () => pm.expect(pm.response.json().through_phase).to.equal(1));
// Save run_id for subsequent requests
pm.environment.set("run_id", pm.response.json().run_id);
```

**422 trigger tests (should return 422):**
```json
// Missing known_positives
{ "disease": "pancreatic cancer", "known_positives": [] }

// Invalid provider
{ ..., "provider": "local" }

// Invalid indication_type
{ ..., "indication_type": "neurology" }

// Empty disease
{ "disease": "", "known_positives": ["KRAS","TP53","SMAD4","CDKN2A","BRCA2"] }
```

---

### 6. GET /api/runs/{run_id}

**Purpose:** Run header + phase statuses.

**Expected response (200):**
```json
{
  "run": {
    "id": "uuid",
    "disease_name": "pancreatic cancer",
    "status": "completed|running|failed|pending",
    "current_phase": 1,
    "intent_mode": "explore",
    "efo_id": "EFO_0002618"
  },
  "phases": [
    { "phase": 0, "status": "completed", "started_at": "...", "finished_at": "..." },
    { "phase": 1, "status": "completed", "started_at": "...", "finished_at": "..." }
  ],
  "running": false
}
```

**Postman assertions:**
```javascript
pm.test("Status 200", () => pm.response.to.have.status(200));
pm.test("Run object present", () => pm.expect(pm.response.json().run).to.be.an('object'));
pm.test("Phases array present", () => pm.expect(pm.response.json().phases).to.be.an('array'));
pm.test("Phase 0 completed", () => {
  const p0 = pm.response.json().phases.find(p => p.phase === 0);
  pm.expect(p0.status).to.equal('completed');
});
```

**Auth tests:**
- No token → `401`
- Wrong run_id → `404`
- Another user's run_id → `404` (not 403 — existence is not leaked)

---

### 7. GET /api/runs/{run_id}/targets

**Purpose:** Ranked target list with evidence trails.

**Expected response (200):**
```json
{
  "targets": [
    {
      "rank": 1,
      "symbol": "KRAS",
      "ensembl_id": "",
      "aggregate_score": 0.923,
      "validation_score": null,
      "tdl": "Tclin",
      "modality_primary": "unknown",
      "modality_secondary": null,
      "evidence_trail": {
        "xgb_probability": 0.923,
        "pu_bio_score": 0.923,
        "pu_percentile": 99.1,
        "tractability": 0.8,
        "genetic": 0.75,
        "ppi_eigenvector": 0.91,
        "shap_top": [{ "feature": "essentiality", "value": 0.32 }]
      }
    }
  ]
}
```

**Postman assertions:**
```javascript
pm.test("Status 200", () => pm.response.to.have.status(200));
pm.test("Targets array non-empty", () => pm.expect(pm.response.json().targets.length).to.be.above(0));
pm.test("Each target has rank", () => {
  pm.response.json().targets.forEach(t => pm.expect(t.rank).to.be.a('number'));
});
pm.test("xgb_probability present (fix verification)", () => {
  const t = pm.response.json().targets[0];
  pm.expect(t.evidence_trail.xgb_probability).to.be.a('number');
});
pm.test("Known positives in top 20", () => {
  const symbols = pm.response.json().targets.map(t => t.symbol);
  pm.expect(symbols).to.include('KRAS');
});
```

---

### 8. GET /api/runs/{run_id}/decisions

**Purpose:** LLM gate audit trail.

**Expected response (200):**
```json
{
  "decisions": [
    {
      "phase": 2,
      "gate": "2.8_tractability_edge_KRAS",
      "llm_provider": "lmstudio",
      "llm_model": "qwen/qwen3-4b-thinking-2507",
      "decision_json": {
        "primary_recommendation": "SM",
        "confidence": 0.85,
        "key_reasoning": "..."
      },
      "created_at": "..."
    }
  ]
}
```

---

### 9. GET /api/runs/{run_id}/compute

**Purpose:** Cost and wall-time log per phase step.

**Expected response (200):**
```json
{
  "compute": [
    { "phase": 1, "step": "phase1_complete", "service": "local", "cost_usd": 0.0, "wall_time_s": 892.3 }
  ]
}
```

---

### 10. GET /api/runs/{run_id}/events

**Purpose:** Polling fallback for event replay (when WebSocket not available).

**Expected response (200):**
```json
{
  "events": [
    { "seq": 0, "ts": 1234567890, "type": "run", "status": "running" },
    { "seq": 1, "ts": 1234567891, "type": "phase", "phase": 0, "status": "running" }
  ],
  "running": false,
  "done": true
}
```

---

### 11. WS /api/runs/{run_id}/stream

**Purpose:** Live event stream via WebSocket.

**Postman WebSocket test:**
1. Connect to `ws://localhost:8000/api/runs/{{run_id}}/stream`
2. First messages should be buffered replays (type: `log`, `phase`, `run`)
3. Then one `{"type": "synced", "running": false, "done": true}` sentinel
4. On active run: live events arrive as they happen

**Assertions:**
- Connection accepted (101 Upgrade)
- `synced` event received within 5s
- `done: true` once run is finished

---

### 12. POST /api/module-runs

**Purpose:** Single-phase isolated run.

**Expected response:** `501 Not Implemented`
```json
{ "detail": "Single-module runs are not supported yet..." }
```

This is intentional. Test that the 501 is returned cleanly (not 500).

---

## Postman Collection Structure

```
RxDis API
├── Health
│   ├── GET /api/health                    ← smoke test
│   └── GET /api/system/telemetry
├── Auth
│   ├── POST /api/runs (no token → 401)
│   └── GET /api/runs/{id} (wrong user → 404)
├── Gene Search
│   ├── GET /api/genes?q=KRAS
│   ├── GET /api/genes?q=           ← empty
│   └── GET /api/genes?q=ZZZNOTREAL ← miss
├── Runs — Happy Path
│   ├── POST /api/runs (creates run, saves run_id)
│   ├── GET /api/runs
│   ├── GET /api/runs/{{run_id}}
│   ├── GET /api/runs/{{run_id}}/targets
│   ├── GET /api/runs/{{run_id}}/decisions
│   └── GET /api/runs/{{run_id}}/compute
├── Runs — 422 Validation
│   ├── POST /api/runs (provider=local)    ← expect 422
│   ├── POST /api/runs (indication=neuro)  ← expect 422
│   ├── POST /api/runs (no positives)      ← expect 422
│   └── POST /api/runs (empty disease)     ← expect 422
└── Module Runs
    └── POST /api/module-runs              ← expect 501
```
