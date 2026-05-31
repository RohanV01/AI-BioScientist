# Phase 1 — Target Identification: Summary

**Last updated:** 2026-05-31
**Status:** Code complete · end-to-end validated on pancreatic cancer + breast cancer
**PRD:** `docs/PRD_phase1_target_id.md`
**Source:** `src/phases/phase1/`
**Bottlenecks log:** `bottlenecks/phase1.md`

---

## Architecture: Tabular PU-Learning

Phase 1 replaced an NLP/literature map-reduce design (retired 2026-05-31) with a
**deterministic, CPU-only** pipeline. No LLM is required for target scoring;
LLM gates remain optional for disease EFO disambiguation only.

### Why this architecture
1. **VRAM** — 4B LLM OOM-prone on 6 GB RTX 3050; PU model is CPU/RAM only
2. **Anti-streetlight** — literature biases toward well-studied genes; PU scores
   by multi-omics *similarity* to known targets, surfaces dark-genome hits
3. **Reproducibility** — deterministic bagging-PU with fixed seed; same positives
   always produce same ranking

---

## Pipeline steps

| Step | Module | What it does |
|---|---|---|
| 1.1 | `disease_normalization.py` | Disease name → EFO ID via Open Targets. Skipped if `disease_efo_id` is set in RunConfig. |
| 1.2 | `open_targets.py` | OT `associatedTargets` → tractability score + `genetic_association` datatype score per gene + DOID cross-refs for Jensen DISEASES lookup |
| 1.3 | `matrix.py` | Assemble 19,699 × 518 float32 feature matrix: STRING spectral embedding (512-d) + DepMap Chronos (2) + GTEx log-TPM (2) + AlphaMissense pathogenicity (2) |
| 1.4 | `pu_model.py` | Bagging-PU LightGBM (default 30 bags). Returns ranked scores + SHAP attributions. AUROC(LOO) ≥ 0.98 on validated diseases. |
| 1.5 | `causal_filter.py` | DoRothEA master-regulator annotation (decoupleR 2.x, cached) |
| 1.6 | `genetic_evidence.py` | GWAS Catalog local TSVs + OMIM mim2gene.txt + Jensen DISEASES (3 files) + OT genetic_association score. Merged into per-gene `genetic` evidence score. |
| 1.7 | `runner.py` | PPI eigenvector proxy (STRING embedding dim-0, min-max normalised) |
| 1.8 | `runner.py` | Rank by PU probability, apply 0.5 floor, assemble evidence trails, persist to Supabase |

---

## Feature matrix (518 columns, 41.9 MB)

| Block | Cols | Source | Notes |
|---|---|---|---|
| STRING spectral embedding | 512 | `Databases/string/string_node2vec_512.parquet` (48 MB) | One-time precompute via `scripts/precompute_string_embedding.py` |
| DepMap Chronos essentiality | 2 | `Databases/depmap/CRISPRGeneEffect.csv` (440 MB) | `chronos_median`, `selective_fraction`; float32 after read |
| GTEx global expression | 2 | `Databases/gtex/gtex_gene_stats.parquet` (cache) | Streamed once from `GTEx_Analysis_...gene_tpm.parquet` (74k × 19k samples) |
| AlphaMissense pathogenicity | 2 | `Databases/alphamissense/am_gene_stats.parquet` (cache, 0.4 MB) | One-time stream of 5.2 GB TSV → 18,946 genes; uses HGNC UniProt map |

---

## Genetic evidence sources (step 1.6)

| Source | Type | Coverage | Notes |
|---|---|---|---|
| GWAS Catalog (local) | Genetic associations | 124 genes / pancreatic cancer | 669 MB year-split TSVs on disk; searches EFO URI + MONDO IDs + disease name |
| OMIM mim2gene.txt | Mendelian disease | ~200 genes / query | No API key required; 0.4 score for any gene with a dedicated OMIM entry |
| Jensen DISEASES | Curated + experimental + text-mining | 10,000+ genes / common cancers | 3 TSVs (9.2 MB total) downloaded from `download.jensenlab.org`; no API key, no rate limits |
| Open Targets `genetic_association` | GWAS + genetics portal | ~300 genes / disease | Already fetched in step 1.2; zero extra API calls |

**DisGeNET removed 2026-05-31.** Free tier rate limit (10 requests/day) was incompatible with iterative development. Jensen DISEASES provides equivalent or broader coverage with no restrictions.

---

## Validated runs

### Run 1 — Pancreatic cancer (2026-05-31)
Positives: KRAS, TP53, SMAD4, CDKN2A, BRCA2 · 20 bags · 20 targets
- **AUROC(LOO): 0.994** · Wall time: 53s · 20 targets persisted
- Top novel hits: AKT1, BRCA1, HIF1A, SMAD3, RAD51, MDM2
- 4/10 top hits are master regulators (TP53, SMAD4, HIF1A, SMAD3) ✓

### Run 2 — Breast cancer (2026-05-31)
Positives: BRCA1, BRCA2, TP53, PIK3CA, ERBB2 · 20 bags · 20 targets
- **AUROC(LOO): 0.995** · Wall time: 57s · 20 targets persisted
- Top novel hits: EGFR, GRB2, ATM, STAT3, RAD51, PTEN, CDK1, PLK1
- All 5 known positives ranked 1–5 ✓
- Genetic scores populated: BRCA2=0.92, EXO1=0.83, ATM=0.70, RAD51=0.70 ✓
- RAD51 essential (ess=−1.23), CDK1 highly essential (ess=−2.63), PLK1 highly essential (ess=−2.78) ✓

---

## Performance profile

| Step | Time (warm) | RAM | Notes |
|---|---|---|---|
| Feature matrix | ~7s | 42 MB | GTEx + AlphaMissense from parquet cache |
| PU learning (30 bags) | ~4s | 250 MB peak | LightGBM; all CPU cores |
| DoRothEA annotation | <1s | — | From cached 0.4 MB parquet |
| Genetic evidence | ~5s | — | GWAS scan 669 MB + DISEASES 9 MB; OT 1 HTTP |
| DB persistence | ~2s | — | 20 plain inserts after `clear_targets()` |
| **Total (warm)** | **~55s** | **< 500 MB** | Matrix cache built; no LM Studio needed |

First cold run: ~3 min (GTEx stream 52s + AlphaMissense stream 37s, both one-time).

---

## Output contract (evidence_trail per target)

```json
{
  "xgb_probability": 0.968,
  "pu_percentile": 0.999,
  "dorothea_activity": 0.42,
  "is_master_regulator": false,
  "regulon_size": 0,
  "dorothea_confidence": "",
  "shap_top": [{"feature": "emb_0", "value": 0.0312}, ...],
  "essentiality": -0.465,
  "selective_fraction": 0.28,
  "expression": 3.14,
  "tractability": 0.65,
  "genetic": 0.74,
  "ppi_eigenvector": 0.82
}
```

Phase-2 compat keys **tractability**, **genetic**, **ppi_eigenvector** are always populated (0.0 default). Phase 3 reads nothing from Phase 1.

---

## How to run

**Via the React Studio:**
```bash
./scripts/run_studio.sh dev          # API :8000 + UI :5173
./scripts/run_studio.sh              # single process at :8000
```

**Via CLI:**
```bash
.venv/bin/python scripts/kickoff.py --disease "breast cancer" --through 1
```

## File map
```
src/phases/phase1/
├── runner.py                   # orchestrator (steps 1.1–1.8)
├── disease_normalization.py    # 1.1
├── open_targets.py             # 1.2: OT associations + tractability + xrefs
├── matrix.py                   # 1.3: 518-feature float32 matrix
├── pu_model.py                 # 1.4: bagging-PU LightGBM + SHAP
├── causal_filter.py            # 1.5: DoRothEA master-regulators
└── genetic_evidence.py         # 1.6: GWAS + OMIM + Jensen DISEASES + OT-GA
Databases/
├── string/string_node2vec_512.parquet        # 48 MB STRING embedding
├── depmap/CRISPRGeneEffect.csv               # 440 MB DepMap
├── gtex/gtex_gene_stats.parquet              # 1.1 MB GTEx cache
├── alphamissense/am_gene_stats.parquet       # 0.4 MB AlphaMissense cache
├── gwas_catalog/*associations*.tsv           # 669 MB GWAS year-splits
├── omim/mim2gene.txt                         # 1 MB OMIM
├── omim/hgnc_complete_set.txt                # 1.1 MB HGNC UniProt map
└── diseases_jensen/
    ├── human_disease_knowledge_filtered.tsv  # 590 KB curated
    ├── human_disease_experiments_filtered.tsv # 2.8 MB experimental
    └── human_disease_textmining_filtered.tsv  # 5.8 MB text-mining
```
