# PRD — Phase 1: Target Identification (Tabular PU-Learning Architecture)

**Maps to:** Human Pipeline.md §PHASE 1 — *rearchitected 2026-05-31*
**Celery queue:** `cpu` (matrix assembly, Node2Vec, tree models, decoupleR) · `llm` **optional** (EFO disambiguation, master-regulator narrative only)
**Depends on:** Phase 0 `go_no_go: "go"`
**Supersedes:** the NLP/literature map-reduce design (Phase 1.4) — see *Architectural Pivot* below.

---

## Architectural Pivot (why this exists)

The previous Phase 1 mined PubMed/Europe PMC abstracts with a local-LLM map-reduce
(old steps 1.4 extraction/merge). It was retired because:

1. **VRAM/RAM OOM risk.** A 4B local model on a 6 GB RTX 3050 (~2.3 GB free) is a
   single point of failure; ~70 s/call × hundreds of abstracts = multi-hour runs that
   routinely OOM or stall (see `bottlenecks/phase1_run_2026-05-31.md`, B2/B8/B11).
2. **The streetlight effect.** Literature signal rewards *how well-studied* a gene is,
   not *how promising* it is — structurally biasing against novel/Tdark targets, which
   is the opposite of the platform's goal.
3. **Non-reproducibility.** Local-LLM JSON was unreliable (B2: 3/4 chunks dropped → 1 gene).

**The replacement** is a deterministic, memory-bounded, **tabular Positive-Unlabeled (PU)
learning** pipeline over a fused **network-embedding + multi-omics** feature matrix. It runs
**entirely on CPU/RAM** (LM Studio can be OFF), is reproducible (seeded), and surfaces
hidden targets that share the multi-omics *signature* of known validated targets rather
than their citation count.

---

## Goal

From (a) a disease and (b) a small set of **known validated targets** ("positives",
5–10 genes), produce a **ranked list of up to `target_count_max` candidate targets** scored
by a PU classifier over a ~20,000-gene feature matrix, each annotated with SHAP feature
attributions and a causal (transcription-factor master-regulator) flag.

This is the most important phase for quality — bad targets here waste all downstream compute.

---

## Inputs Required From You

### Software (Python env — see `bottlenecks/phase1.md` for the env decision)
- `lightgbm` **or** `xgboost` (PU base estimator) · `scikit-learn` · `shap`
- `pandas` ✓ · `numpy` ✓ · `pyarrow` ✓ · `networkx` ✓ (installed)
- Network embedding: gensim-free **NetMF/SVD spectral embedding** via `scipy.sparse` + sklearn `TruncatedSVD` (node2vec ≡ implicit matrix factorization). *`gensim`/`pecanpy`/`node2vec` have no Python 3.14 wheel (confirmed 2026-05-31) — this is the 3.14-native equivalent.*
- `decoupler` (+ `omnipath` on first run) for DoRothEA TF-activity / regulons

### Data (local files)
| Layer | File / source | Status |
|---|---|---|
| PPI network (Node2Vec source) | `Databases/string/9606.protein.links.detailed.v12.0.txt` | ✓ present (868 MB) |
| **Node2Vec embeddings (512-d)** | *generated once from STRING → cached parquet* | ✗ build step (not a download) |
| Essentiality | `Databases/depmap/CRISPRGeneEffect.csv` | ✓ present (440 MB) |
| Expression | `Databases/gtex/..._gene_tpm.parquet` | ✓ present |
| Variant constraint | `Databases/alphamissense/AlphaMissense_hg38.tsv` | ✓ present |
| Methylation / extra omics | **Harmonizome** `gene_attribute_matrix` (per dataset) | ✗ optional download |
| TF regulons | DoRothEA via `decoupler`/`omnipath` (cached parquet) | ✗ first-run fetch |
| Gene ID map | HGNC symbol ↔ Ensembl gene/protein ↔ UniProt | ✗ build/download once |

### Accounts / APIs (free, optional, **no LLM required**)
- Open Targets GraphQL — *optional* thin annotation pull for the `tractability` hint only
  (no auth, 1 call/run; kept solely to feed Phase 2's pocket fallback — see I/O contract).
- LM Studio — *optional*, only if EFO disambiguation or the master-regulator narrative gate
  is enabled. The core pipeline runs with it off.

### Configuration (RunConfig additions — see §Config below)
- `known_positives: List[str]` — the 5–10 validated targets that anchor the PU model.
- `disease_efo_id` (optional; auto-resolved from `disease_name` if absent).

---

## Data Flow

```
disease + known_positives
        │
  1.1 resolve EFO + load positive set
        │
  1.2 assemble FEATURE MATRIX  ── 1.3 Node2Vec(STRING, 512-d, cached)
        │  (~20k genes × [512 embedding + N omics], float32, RAM-bounded)
        ▼
  1.4 PU LEARNING  (LightGBM/XGBoost, positives vs unlabeled)
        │  → P(target) for every gene
        ▼
  1.5 SHAP attributions on top hits
        ▼
  1.6 CAUSAL FILTER  (decoupleR + DoRothEA → TF master-regulator flag/score)
        ▼
  1.7 rank → top-N → output_json + `targets` rows  ──▶ Phase 2
```

---

## Process Steps

### 1.1 Disease resolution & positive set
- If `disease_efo_id` set → use it. Else Open Targets `search` → EFO; `1.1_efo_disambiguation`
  LLM gate **only** if multiple EFO ≥0.6 (optional; deterministic top-hit fallback if LLM off).
- Load `known_positives` (validated targets). Validate each resolves to a row in the gene
  universe; warn on any that don't. **PU needs ≥5 positives** for a stable model; <5 → warn
  and widen via `seed_targets` ∪ known_positives.

### 1.2 Feature matrix assembly — "The Matrix"
- **Gene universe:** ~20,000 protein-coding genes from the canonical HGNC list; one row per gene.
- **Unified key:** HGNC symbol (with Ensembl-gene + UniProt cross-refs). All sources mapped
  onto this key via the ID map (STRING ENSP → gene; GTEx ENSG → gene; DepMap symbol; etc.).
- **Merge feature blocks** into one `float32` DataFrame:
  - Node2Vec embedding (512 cols) — from §1.3.
  - Essentiality — DepMap Chronos median + selective-dependency fraction.
  - Expression — GTEx tissue profile (+ `tissue_of_interest` columns).
  - Constraint — AlphaMissense mean/`high_path` fraction.
  - Methylation / extra omics — Harmonizome blocks (optional; `NaN`→impute).
  - Network scalars — STRING degree + eigenvector centrality (cheap on the conf-filtered graph).
- **Memory discipline (hard requirement, see `bottlenecks/phase1.md`):** chunked reads of the
  868 MB/440 MB files, `float32`/`category` dtypes, no full-matrix copies, drop intermediates.

### 1.3 STRING Node2Vec embedding (one-time, cached)
- Build the graph from `9606.protein.links.detailed.v12.0.txt` at `combined_score ≥ 700`
  (or the chosen confidence floor); map ENSP→gene.
- Compute a 512-d **NetMF/SVD spectral embedding** (gensim-free): build the sparse symmetric-normalized adjacency from the conf-filtered graph → `TruncatedSVD(n_components=512)`. node2vec ≡ implicit factorization of the PPMI matrix (Qiu et al. 2018), so this is the 3.14-native equivalent.
- **Cache to `Databases/string/string_node2vec_512.parquet`** keyed by gene symbol. Regenerated
  only if missing or the confidence floor changes. This is the single CPU-heavy precompute.

### 1.4 PU Learning core — target scoring
- **Positives** = `known_positives` (label 1). **Unlabeled** = all other genes (label 0/unlabeled).
- **Estimator:** LightGBM (default; lower RAM) or XGBoost. **PU method:** bagging-PU
  (Mordelet–Vert) or two-step (spy → reliable negatives → classifier). Cross-validated AUROC
  reported via leave-one-positive-out.
- Output: calibrated `P(target | features)` for **every** gene, plus a within-run percentile.
- Reproducible: fixed `random_state`; no stochastic LLM in the loop.

### 1.5 SHAP attributions
- `shap.TreeExplainer` on the top hits → per-gene top contributing features
  (e.g. "neighbour of KRAS in PPI space", "pancreas-selective expression", "selective DepMap
  dependency"). Drives the **SHAP drawer** in the UI (DESIGN.md View 3).

### 1.6 Causal filter — master-regulator (TF) verification
- Load DoRothEA regulons (confidence A/B/C) via `decoupler`.
- **Default (no signature needed):** flag hits that are high-confidence TFs with a substantial
  regulon (`is_master_regulator`, `regulon_size`) — the "regulatory master switch" test.
- **Upgrade (if `patient_cohort.expression_matrix` provided):** run `decoupler` ULM/MLM
  (the matrix-multiplication step) to compute true TF **activity** (NES) and rank master
  regulators by activity. Optional `1.6_master_regulator` LLM narrative gate (deterministic if off).

### 1.7 Rank, select, persist
- Final score = PU probability, with an optional small master-regulator boost (intent-aware).
- Select top `target_count_max`; `known_positives`/`seed_targets` always included (`seeded=true`);
  `exclude_targets` removed.
- Write `output_json` (below) + one `targets` row per selected gene.

---

## Local-LLM Decision Points (now minimal — pipeline is LLM-optional)

| Gate | When | Decision | Output schema |
|---|---|---|---|
| `1.1_efo_disambiguation` | multiple EFO ≥0.6 **and** LLM enabled | pick disease ontology id | `{selected_efo_id, reason}` |
| `1.6_master_regulator` | top hits include TFs **and** LLM enabled | plain-English "why this is a master switch" | `{summary}` |

Everything else is deterministic. With the provider off, both gates fall back to rules.

---

## Config (RunConfig additions)

```json
{
  "disease_name": "pancreatic cancer",
  "disease_efo_id": "EFO_0002618",
  "intent_mode": "explore",
  "known_positives": ["KRAS", "TP53", "SMAD4", "CDKN2A", "BRCA2"],
  "seed_targets": [],
  "exclude_targets": [],
  "tissue_of_interest": "Pancreas",
  "indication_type": "oncology",
  "target_count_max": 20,
  "phase1": {
    "pu_method": "bagging",
    "base_estimator": "lightgbm",
    "node2vec_dim": 512,
    "string_confidence_min": 700,
    "use_harmonizome": true,
    "dorothea_confidence": ["A", "B", "C"]
  }
}
```

`known_positives` is the new required-for-quality field (the PU anchor / DESIGN.md View 1
dual-list). If empty, it falls back to `seed_targets`.

---

## I/O Contract

**Input:** Phase 0 output + RunConfig (with `known_positives`).

**Output (`phase_results.output_json` for phase 1):**
```json
{"ranked_targets":[
  {"rank":1,"ensembl_id":"ENSG00000133703","symbol":"KRAS",
   "aggregate_score":0.94,"modality_hint":"SM","tdl":"Tclin","seeded":true,
   "evidence_trail":{
     "xgb_probability":0.94,"pu_percentile":0.999,
     "dorothea_activity":2.1,"is_master_regulator":false,"regulon_size":0,
     "essentiality_chronos":-0.71,"string_degree":118,
     "shap_top":[{"feature":"node2vec_dim_137","value":0.09},
                 {"feature":"gtex_pancreas","value":0.06}],
     "tractability":1.0, "genetic":0.0, "ppi_eigenvector":0.99
   }}
],
"efo_id":"EFO_0002618","disease_label":"pancreatic carcinoma",
"model":{"method":"bagging-PU","estimator":"lightgbm","auroc_loo":0.91,
         "n_positives":5,"n_genes":19990},
"causal_filter":{"n_master_regulators":3},
"feature_matrix":{"rows":19990,"cols":561,"peak_ram_mb":1840},
"wall_time_s":612}
```
Also writes one row per target into `targets` (via `run_state.upsert_target`).

> **Phase-2 compatibility (do not drop these):** `evidence_trail.tractability`,
> `.genetic`, `.ppi_eigenvector` are consumed by Phase 2
> ([phase2/runner.py:82](../src/phases/phase2/runner.py#L82),
> [phase2/scoring.py:60-61](../src/phases/phase2/scoring.py#L60-L61)). They are kept in the
> trail (populated from the optional OT pull, local GWAS/OMIM, and the STRING subgraph) so
> Phase 2 needs **no code change**. New keys (`xgb_probability`, `dorothea_activity`, etc.)
> are additive.

---

## Success Criteria

1. **Driver recovery (leave-one-out):** positives `{KRAS,TP53,SMAD4}` for pancreatic cancer →
   held-out `CDKN2A` (and other canonical drivers) appear in the top ranks.
2. **Novelty:** ≥3 of the top-20 are Tbio/Tdark (understudied) genes that share the positives'
   omics signature — i.e. the model surfaces hidden targets, not just citation-heavy ones.
3. **Hardware:** peak process RAM **< 10 GB** on 16 GB system; **0 GB VRAM** (LM Studio off).
4. **Reproducibility:** identical top-10 across two runs with the same seed and pinned data.
5. **Resilience:** missing Harmonizome → degrades to local omics; DoRothEA fetch fail →
   static TF membership; <5 positives → warns but still runs.
6. **Hand-off:** Phase 2 consumes the output unchanged (compat keys present).

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| Node2Vec cache missing | trigger §1.3 precompute (logged; one-time cost) |
| <5 known_positives | warn; union with `seed_targets`; report reduced AUROC confidence |
| Harmonizome blocks absent | impute `NaN`; proceed on local omics (GTEx/DepMap/AlphaMissense) |
| DoRothEA/omnipath fetch fail | fall back to a static HGNC TF list for the master-regulator flag |
| ID-map gaps (gene not resolvable) | drop from universe with a logged count; never crash the merge |
| Peak RAM nearing ceiling | reduce Node2Vec dim / increase chunking / cast to float32 (see bottleneck doc) |
| No EFO match | proceed PU-only (EFO is metadata here); optional OT annotation skipped |
