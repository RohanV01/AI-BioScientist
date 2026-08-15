# Phase 1 — Target Identification: Summary

**Last updated:** 2026-06-01
**Status:** Code complete · validated on pancreatic cancer, breast cancer, Parkinson's disease
**PRD:** `docs/PRD_phase1_target_id.md`
**Source:** `src/phases/phase1/`
**Bottlenecks log:** `bottlenecks/phase1.md`
**Scientific methodology:** `Scientific Protocol/phase1_target_identification.md`

---

## Architecture: Biological Fingerprint PU-Learning (v2, 2026-06-01)

Phase 1 produces a ranked list of candidate drug targets for a given disease by learning
the **biological fingerprint** of confirmed disease-associated genes and finding unlabelled
genes that share that profile.

### Core design decisions

| Decision | Rationale |
|---|---|
| Positive-Unlabeled (PU) learning | No reliable negative drug targets exist — only unlabelled genes |
| 14 disease-agnostic biological features | Replaces 512-d STRING embedding which encoded literature bias (textmining r=0.66 with combined_score) |
| OT-GA positive set expansion | Expands from 5 user seeds to 15-80 confirmed positives, forcing all 14 features to contribute |
| Two independent output scores | `pu_bio_score` (biological similarity) kept separate from `ot_genetic_assoc` (genetic evidence) |
| No LLM required | CPU/RAM only; deterministic; reproducible with fixed seed |

### Why v1 (STRING embedding) was retired

The original Phase 1 used a 512-dimensional STRING Node2Vec embedding as the primary feature
block. Diagnostic analysis revealed:
1. STRING `textmining` channel has the highest correlation with combined_score (r=0.662),
   meaning the embedding encoded literature co-mention patterns — the opposite of the intended anti-streetlight design.
2. With 5 positives and OT-GA as a feature, the model collapsed to a single-feature classifier:
   LightGBM used OT-GA in the first split and never touched essentiality, expression, or constraint.
   11 of 16 features had zero information gain.
3. LOO-AUROC of 0.999 was evaluating whether OT-GA-positive genes outrank OT-GA-zero genes —
   a trivially easy task, not a meaningful model quality metric.

---

## Pipeline steps

| Step | Module | What it does |
|---|---|---|
| 1.1 | `disease_normalization.py` | Disease name → EFO/MONDO ID via OT search. Skipped if `disease_efo_id` set. |
| 1.2 | `open_targets.py` | OT pull → `ot_genetic_map`, `tractability_map`, DOID/MONDO xrefs |
| 1.2b | `runner.py` | Expand positive set: user seeds + all OT-GA ≥ 0.5 genes |
| 1.3 | `matrix.py` | Assemble 19,699 × 14 float32 feature matrix (all disease-agnostic) |
| 1.4 | `pu_model.py` | Bagging-PU LightGBM (30 bags). Returns `pu_bio_score` + SHAP. |
| 1.5 | `causal_filter.py` | DoRothEA master-regulator annotation (TF activity, cached parquet) |
| 1.6 | `genetic_evidence.py` | GWAS + OMIM + Jensen DISEASES + OT-GA → `genetic` compat key |
| 1.7 | `runner.py` | STRING degree centrality (combined_score ≥ 700) → `ppi_eigenvector` |
| 1.7b | `open_targets.py` | Pharos TDL annotation → `tdl` field per target |
| 1.8 | `runner.py` | Rank by `pu_bio_score`, build evidence trails, persist to Supabase |

---

## Feature matrix — 14 columns, 2.3 MB

All features are **disease-agnostic** (computed once, cached, reused across all diseases).
Disease-specific signals (`ot_genetic_assoc`, `ot_tractability`) are stored in the evidence trail
only — never used as training features, preserving independence of the two output scores.

| Feature | Source file | Biology captured | First-run | Warm |
|---|---|---|---|---|
| `string_exp_degree` | STRING links detailed | Physical interactions (experimental channel only, score ≥ 200) | ~20s | <0.1s |
| `string_db_degree` | STRING links detailed | Curated pathway database interactions | ~20s (shared) | <0.1s |
| `string_coexp_degree` | STRING links detailed | Co-expression across tissues | ~20s (shared) | <0.1s |
| `biogrid_degree` | BioGRID TAB3 | Independent experimental PPI (physical only) | ~5s | <0.1s |
| `primekg_disease_degree` | PrimeKG kg.csv | # distinct disease nodes connected (hub proxy) | ~15s | <0.1s |
| `primekg_pathway_degree` | PrimeKG kg.csv | # distinct pathway nodes connected | ~15s (shared) | <0.1s |
| `essentiality` | DepMap CRISPR | Chronos median across cancer cell lines | ~3s | ~3s |
| `selectivity` | DepMap CRISPR | Fraction of cell lines where essential | ~3s (shared) | ~3s |
| `expression` | GTEx parquet | log1p(mean TPM) across normal tissues | 52s stream | <0.1s |
| `pct_expressed` | GTEx parquet | Fraction of samples expressing gene | 52s (shared) | <0.1s |
| `am_pathogenicity` | AlphaMissense TSV | Mean missense variant pathogenicity | 37s stream | <0.1s |
| `am_high_path_frac` | AlphaMissense TSV | Fraction of variants predicted pathogenic | 37s (shared) | <0.1s |
| `chembl_max_phase` | ChEMBL sqlite | Highest clinical phase of any drug (0–1, /4) | ~2s | <0.1s |
| `is_mendelian` | OMIM mim2gene.txt | Binary: confirmed Mendelian disease gene | <1s | <1s |

All features log1p-normalised where appropriate (degree counts). Missing values → 0.0 ("no evidence").

---

## Positive set expansion (step 1.2b)

The OT-GA expansion is the critical change enabling all 14 features to contribute:

```
user_positives (5–10 validated targets, domain knowledge)
    +
OT genes with genetic_association ≥ 0.5 (OT-confirmed disease genes)
    =
all_positives (15–80 depending on disease breadth)
```

| Disease | User seeds | OT-GA ≥ 0.5 added | Total positives | AUROC(LOO) |
|---|---|---|---|---|
| Pancreatic cancer | 5 | 26 | 31 | 0.880 |
| Breast cancer | 5 | 72 | 77 | 0.915 |
| Parkinson's disease | 5 | 66 | 71 | 0.755 |

AUROC(LOO) now reflects genuine biological diversity — Parkinson's is lower (0.755) because
PD targets are biologically heterogeneous (lysosomal, mitochondrial, aggregation biology)
with no single discriminating feature. Cancer targets are more homogeneous (DNA repair, cell
cycle, tumor suppression), yielding higher but still honest AUROC.

---

## Feature importance across diseases (confirmed non-zero for all)

| Feature | Pancreatic gain | Breast gain | Parkinson's gain | What this tells us |
|---|---|---|---|---|
| `primekg_disease_degree` | 328 (top) | 1000 (top) | 192 | Disease gene connectivity universal; dominant signal |
| `string_exp_degree` | 83 | 110 | **195 (top)** | PD targets have distinctive co-expression |
| `essentiality` | 33 | 66 | **174** | PD targets have specific essentiality; cancer more variable |
| `gtex_log_mean_tpm` | 63 | 94 | **151** | Neuronal expression fingerprint in PD |
| `am_mean_pathogenicity` | 20 | 76 | **117** | Constraint matters more in neurodegeneration |
| `biogrid_degree` | 22 | 97 | 114 | Physical interaction hub-ness |
| `chembl_max_phase` | 0.2 | 4 | 9 | Clinical precedent — weak but non-zero |
| `is_mendelian` | 0.4 | 0.2 | 3 | Non-zero for all diseases |

No features have zero gain. This is the key improvement over v1.

---

## Two-score output system

Each target receives two independent scores in its evidence trail:

```
pu_bio_score      — biological similarity to confirmed disease targets
                    trained on 14 disease-agnostic features
                    range: 0–1 (bagged LightGBM mean probability)

ot_genetic_assoc  — disease-specific genetic evidence from Open Targets
                    NOT used as a training feature; stored separately
                    range: 0–1 (OT integrated genetics portal score)
```

**Interpretation matrix:**

| pu_bio_score | ot_genetic_assoc | Category | Action |
|---|---|---|---|
| High | High | High-confidence target | Priority Phase 2 candidates |
| High | 0 | Novel hypothesis | Biology fits; genetics unconfirmed — Phase 2 validates |
| Low | High | Genetically confirmed, atypical biology | Proceed to Phase 2 with caution |
| Low | 0 | No signal | Not worth pursuing |

---

## Validated runs

### Pancreatic cancer (EFO_0002618)
**Seeds:** KRAS, TP53, SMAD4, CDKN2A, BRCA2 | **Positives:** 31 | **AUROC:** 0.880
- High-confidence (pu_bio + OT-GA): ATM, BRCA1, PALB2, NBN, STK11, CHEK2
- Novel hypotheses (pu_bio high, OT-GA=0): MET, BLM, FANCD2, ERBB3
- Dominant SHAP feature: `primekg_disease_degree`

### Breast cancer (EFO_0000305)
**Seeds:** BRCA1, BRCA2, TP53, PIK3CA, ERBB2 | **Positives:** 77 | **AUROC:** 0.915
- High-confidence: ATM, CDH1, CCNE1, RAD51D, ESR1, MSH2
- Novel hypotheses: ERCC4, IRS1, POT1, CASP8, FAS, RUNX1
- Dominant SHAP feature: `primekg_disease_degree`

### Parkinson's disease (MONDO_0005180)
**Seeds:** LRRK2, SNCA, PINK1, PRKN, GBA | **Positives:** 71 | **AUROC:** 0.755
- High-confidence: MAPT, APOE, ATP13A2, PSAP, BAG3, DNAJC6
- Novel hypotheses: MT-ND2, MT-ND3, MT-ND5, MT-ND6, MT-CYB (mitochondrial Complex I)
- Dominant SHAP feature: `string_exp_degree` (changed from cancer — disease-specific fingerprint)
- Cross-disease check: only ATM shared with cancer top-20. Parkinson's-specific biology confirmed.

---

## Genetic evidence sources (step 1.6)

| Source | Coverage | Notes |
|---|---|---|
| GWAS Catalog (local TSVs) | Varies | 669 MB; searches EFO + MONDO IDs + keyword-contains match |
| OMIM mim2gene.txt | ~193 genes/query | Disease-agnostic flag, score=0.1 (low weight) |
| Jensen DISEASES | ~350 genes / pancreatic | 3 TSVs; disease-specific word matching |
| OT `genetic_association` | ~300 genes / disease | Used as fallback for genes not in GWAS/OMIM/DISEASES |

DisGeNET removed 2026-05-31. Jensen DISEASES substring bug fixed 2026-06-01 (was matching 10k+ genes via `dis_name in disease_key`; now uses specific-word matching).

---

## Performance (warm run, pancreatic cancer)

```
Step                                 Time     Memory
──────────────────────────────────────────────────────────────────
1.1  EFO provided (skip)              <1s      —
1.2  OT pull + MONDO/DOID xrefs       ~5s      —
1.2b Positive set expansion           <1s      —
1.3  14-feature matrix (all cached)   ~3s      2.3 MB
1.4  PU learning (20 bags, 31 pos)   ~30s    150 MB LightGBM
1.5  DoRothEA                         <1s      —
1.6  Genetic evidence                 ~5s      —
1.7  STRING degree (cached)           <1s      —
1.7b Pharos TDL (20 targets)          ~2s      —
1.8  Rank + persist 20 targets        ~3s      —
──────────────────────────────────────────────────────────────────
     TOTAL                           ~50s    ~300 MB peak
```

Cold first-run (one-time only): GTEx +52s, AlphaMissense +37s, STRING channels +20s,
PrimeKG +15s, BioGRID +5s, ChEMBL +2s. All cached to parquet after first run.

---

## Output contract (evidence_trail per target)

```json
{
  "pu_bio_score": 0.987,
  "pu_percentile": 0.999,
  "ot_genetic_assoc": 0.868,
  "is_master_regulator": false,
  "regulon_size": 0,
  "dorothea_confidence": "",
  "shap_top": [
    {"feature": "primekg_disease_degree", "value": 0.42},
    {"feature": "essentiality", "value": -0.23},
    {"feature": "string_exp_degree", "value": 0.18},
    {"feature": "am_pathogenicity", "value": 0.12},
    ...
  ],
  "essentiality": -0.517,
  "selectivity": 0.524,
  "expression": 2.439,
  "tractability": 1.0,
  "genetic": 0.694,
  "ppi_eigenvector": 0.273
}
```

---

## How to run

**Studio (React UI):**
```bash
./scripts/run_studio.sh dev     # API :8000 + hot-reload :5173
```

**CLI:**
```bash
.venv/bin/python scripts/kickoff.py --disease "pancreatic cancer" --through 1
```

---

## File map

```
src/phases/phase1/
├── runner.py               # orchestrator (steps 1.1–1.8)
├── disease_normalization.py
├── open_targets.py         # OT pull + Pharos TDL + disease xrefs
├── matrix.py               # 14-feature biological fingerprint matrix
├── pu_model.py             # bagging-PU LightGBM + SHAP (top-8 interpretable)
├── causal_filter.py        # DoRothEA master-regulator annotation
└── genetic_evidence.py     # GWAS + OMIM + Jensen DISEASES + OT-GA

Databases/
├── string/
│   ├── 9606.protein.links.detailed.v12.0.txt   (channel-level edges)
│   ├── string_channel_degrees.parquet           (cache: exp/db/coexp degree)
│   └── string_degree_centrality.parquet         (cache: high-conf degree for ppi_eig)
├── biogrid/
│   ├── BIOGRID-ORGANISM-Homo_sapiens-5.0.257.tab3.txt
│   └── biogrid_physical_degree.parquet          (cache)
├── primekg/
│   ├── kg.csv                                   (8.1M edges, multi-relation)
│   └── primekg_gene_degrees.parquet             (cache: disease + pathway degree)
├── depmap/CRISPRGeneEffect.csv                  (440 MB, Chronos)
├── gtex/gtex_gene_stats.parquet                 (cache: expression stats)
├── alphamissense/am_gene_stats.parquet          (cache: pathogenicity stats)
├── chembl/
│   ├── chembl_37.db                             (sqlite)
│   └── chembl_gene_maxphase.parquet             (cache)
├── gwas_catalog/*associations*.tsv             (669 MB year-split)
├── omim/mim2gene.txt + hgnc_complete_set.txt
└── diseases_jensen/                             (9.2 MB, 3 files)
```
