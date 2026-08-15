# Prerequisites

Everything that must be true before any phase test can run.

---

## 1. Environment

### Required `.env` keys

| Key | Required for | How to verify |
|-----|-------------|---------------|
| `SUPABASE_URL` | All phases | `GET /api/health` → `supabase: true` |
| `SUPABASE_SERVICE_KEY` | All phases | Same |
| `SUPABASE_ANON_KEY` | Auth (frontend) | Sign-in works |
| `LMSTUDIO_BASE_URL` | Phase 1, 2, 3 LLM gates | LM Studio shows LIVE in sidebar |
| `LMSTUDIO_MODEL` | Same | Model loaded in LM Studio |
| `ANTHROPIC_API_KEY` | If provider=anthropic | Optional |

### Local database files (must exist)

```
Databases/
  string/9606.protein.links.detailed.v12.0.txt    ← Phase 1 PPI network
  string/string_node2vec_512.parquet              ← Phase 1 embeddings (precompute if missing)
  depmap/CRISPRGeneEffect.csv                     ← Phase 2 essentiality
  alphamissense/AlphaMissense_hg38.tsv            ← Phase 2 variants
  gtex/GTEx_Analysis_*_gene_tpm.gct               ← Phase 2 expression
  chembl/chembl_37.db                             ← Phase 4 repurposing
  primekg/kg.csv                                  ← Phase 4 KG query
  human_protein_atlas/metadata/                   ← Phase 2 localization
```

**Check command:**
```bash
python -c "
from src.config import settings
import os
paths = [
    settings.DB_STRING / '9606.protein.links.detailed.v12.0.txt',
    settings.DB_DEPMAP / 'CRISPRGeneEffect.csv',
    settings.DB_ALPHAMISSENSE / 'AlphaMissense_hg38.tsv',
    settings.DB_CHEMBL / 'chembl_37.db',
]
for p in paths:
    status = 'OK' if p.exists() else 'MISSING'
    print(f'{status}: {p}')
"
```

---

## 2. Services

### Start backend
```bash
source .venv/bin/activate
uvicorn src.api.main:app --reload --port 8000
```

Expected log line: `Application startup complete.`

### Start frontend
```bash
cd frontend && npm run dev
```

Expected: `Local: http://localhost:5173/`

### LM Studio (if provider=lmstudio)
- Load model: `qwen/qwen3-4b-thinking-2507` (or whatever is set in `LMSTUDIO_MODEL`)
- Verify: `GET http://localhost:1234/v1/models` → returns model list

---

## 3. Test Fixtures

### Standard run payload (copy-paste into Postman or curl)

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

### Minimal payload (fastest — P0 only, no LLM)
```json
{
  "disease": "pancreatic cancer",
  "known_positives": ["KRAS", "TP53", "SMAD4", "CDKN2A", "BRCA2"],
  "intent_mode": "explore",
  "tissue_of_interest": "Pancreas",
  "indication_type": "oncology",
  "provider": "lmstudio",
  "target_count_max": 5,
  "pu_n_bags": 10,
  "through_phase": 0
}
```

---

## 4. Postman Setup

1. Install Postman desktop app.
2. Run `/postman` skill — it will sync the OpenAPI spec from `GET /openapi.json` and scaffold the collection.
3. Set environment variable `base_url = http://localhost:8000`.
4. Set environment variable `auth_token` — get it from browser DevTools after signing in:
   - Network tab → any `/api/` request → `Authorization: Bearer <token>`

---

## 5. Supabase State Reset (between test runs)

If a previous run left bad state, clean it:

```sql
-- Run in Supabase SQL editor
DELETE FROM phase_results WHERE run_id IN (
  SELECT id FROM runs WHERE disease_name = 'pancreatic cancer'
);
DELETE FROM targets WHERE run_id IN (
  SELECT id FROM runs WHERE disease_name = 'pancreatic cancer'
);
DELETE FROM candidates WHERE run_id IN (
  SELECT id FROM runs WHERE disease_name = 'pancreatic cancer'
);
DELETE FROM runs WHERE disease_name = 'pancreatic cancer';
```

---

## 6. Known Environment Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| `string_node2vec_512.parquet` missing | Phase 1 takes 10+ extra min on first run | Run `python scripts/precompute_string_embedding.py` |
| GTEx tissue medians not precomputed | Phase 2 expression lookup slow | Run `python scripts/precompute_gtex_tissue_medians.py` |
| LM Studio not running | Phase 1 LLM gate times out | Start LM Studio, load model, verify `/v1/models` |
| Supabase free tier cold start | First `GET /api/health` takes 5–10s | Retry once |
