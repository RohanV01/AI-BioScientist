# Phase 1 — Target Identification: Implementation Summary

**Date written:** 2026-05-30  
**Last updated:** 2026-05-31  
**Status:** Code complete — infrastructure ready, pending first live run  
**PRD:** `docs/PRD_phase1_target_id.md`  
**Source files:** `src/phases/phase1/`

---

## What Phase 1 Does

Takes a disease string (e.g. "pancreatic cancer") and produces a **ranked list of up to `target_count_max` candidate drug targets**, each with a full multi-evidence trail. This is the most important phase — poor targets here waste all downstream compute.

---

## Infrastructure Status (as of 2026-05-31)

| Component | Status |
|---|---|
| Supabase project | ✅ Created, schema deployed |
| Redis | ✅ Running (v7.0.15, localhost:6379) |
| `.env` credentials | ✅ Supabase, NCBI filled — OMIM API key pending |
| GWAS Catalog (associations) | ✅ 5 year-split TSVs downloaded (669 MB total) |
| OMIM `mim2gene.txt` | ✅ Downloaded to `Databases/omim/` (29,592 entries) |
| LM Studio / LLM provider | ⏳ Model name to confirm in `.env` |
| First dry run | ⏳ Not yet executed |

---

## Steps Implemented

### 1.1 Disease Normalization (`disease_normalization.py`)
- Queries **Open Targets GraphQL** (`search` endpoint) for candidate EFO IDs with confidence scores.
- If exactly one candidate ≥ 0.6 → use it.
- If multiple candidates ≥ 0.6 → **LLM gate `1.1_efo_disambiguation`** picks the best one and logs reasoning to `decisions` table.
- Fallback: **MONDO/Monarch** REST API if OT returns nothing ≥ 0.6.
- Hard fail if no EFO/MONDO match found after all fallbacks.

### 1.2 Open Targets Association Pull (`open_targets.py`)
- GraphQL `disease(efoId).associatedTargets` — paginated, cap 300 rows.
- Filters: `overall_assoc_score > 0.1` (loosened to 0.05 for rare diseases with < 5 hits).
- `exclude_targets` removed before scoring; `seed_targets` force-included (`seeded=True`).
- Extracts: `ot_assoc_score`, `tractability_max` (SM + AB buckets), `dt_scores` breakdown.

### 1.3 Pharos TDL Annotation (`open_targets.py → annotate_pharos_tdl`)
- Batches all target symbols → Pharos GraphQL for TDL (Tclin/Tchem/Tbio/Tdark).
- If > 70% Tdark → `dark_genome_mode = True` (logged in output JSON).

### 1.4 Literature Mining — MAP-REDUCE (`literature_mining.py`)

**MAP phase:**
1. **PubMed ESearch + EFetch**: disease + (target/biomarker/GWAS/knockout), top 500 abstracts. Uses `NCBI_API_KEY` for 10 req/s (vs 3 req/s without).
2. **Europe PMC**: supplemental open-access abstracts, up to 200.
3. **Semantic Scholar** fallback if < 50 abstracts total.
4. **Relevance prefilter gate `1.4_relevance_prefilter`** (only for small/local models): cheap per-abstract 0–10 score; drop if score < 4 or `keep=False`.
5. Chunk abstracts (8 per chunk for local, 80 for frontier).
6. Per chunk: **LLM gate `1.4_extraction`** → `{gene_symbol, evidence[], literature_score}` schema.
7. Each chunk result persisted to `llm_chunks` table keyed by `(run_id, task, chunk_index)` — **crash-safe resume at any chunk**.

**REDUCE phase:**
- **Local model**: hierarchical tree-merge in groups of 8, repeated until 1 final result.
- **Frontier model** (Claude/OpenAI): single-pass synthesis over all chunk outputs.

**Output**: dict `{gene_symbol → {literature_score, evidence[]}}`.

### 1.5 Genetic Evidence (`genetic_evidence.py`)

**GWAS Catalog** (updated 2026-05-31):
- Now reads and merges all 5 year-split TSV files (`gwas-catalog-download-associations-alt.*.tsv`).
- Uses `MAPPED_TRAIT_URI` column (EFO ontology) to match disease precisely.
- Any hit with p < 5e-8 AND effect > 0.1 → `force_include = True` → gene added regardless of OT score.
- Score formula: `0.6 × (-log10(p) - 1)/10 + 0.4 × effect/2`, capped at 1.0.

**OMIM** (updated 2026-05-31 — no API key required):
- Primary: **local `mim2gene.txt`** (`Databases/omim/mim2gene.txt`, 29,592 entries).
  - Any gene with entry type `gene` → score 0.4 (confirmed Mendelian relevance).
- Fallback: OMIM REST API (if `OMIM_API_KEY` set and local file absent).
- When OMIM API key arrives: richer disease-specific scoring via `genemap2.txt`.

**DisGeNET**: gene-disease association scores (free tier, no auth).

All three sources merged into a single `genetic_score` per gene (max-pool).

### 1.6 PPI Network & Centrality (`ppi_network.py`)
- **STRING** (combined_score ≥ 700 = high confidence) loaded from local file.
- **BioGRID** TAB3 human PPI edges augment STRING.
- **PrimeKG fallback**: for Tdark genes absent from STRING, `kg.csv` (combined format supported) protein-protein edges are used.
- Centrality computed: `degree`, sampled `betweenness` (200 random pivots), `closeness`, `eigenvector`.
- Hubs flagged: eigenvector > 95th percentile AND degree > 50.
- **LLM gate `1.6_hub_interpretation`**: classifies hubs as "broad" (generic, apply penalty) vs "disease_specific" (keep full score).
- **Node2Vec embeddings** computed (64d) for Phase 2 SHAP feature input (optional, skips gracefully if `node2vec` not installed).

### 1.7 Pathway & Multi-Omics (`pathway_analysis.py`)
- **Reactome ContentService REST**: per-gene pathway membership via batched queries.
- Disease-relevant pathways selected based on disease name keywords (cancer/fibrosis/autoimmune/neurodegeneration/metabolic patterns).
- Genes at chokepoints of ≥ 2 disease-relevant pathways receive boosted `pathway_score`.
- Score = `chokepoint_count / max_chokepoints` (normalized 0–1).

### 1.8 Aggregate Scoring & Ranking (`scoring.py`)
- **LLM gate `1.8_weight_tuning`** (critical gate — 2 rounds of self-consistency for small models):
  Adjusts default weights for the `indication_type` (chronic/acute/oncology).
  Default weights: `ot=0.30, lit=0.15, gen=0.15, ppi=0.10, pathway=0.10, tractability=0.10, novelty=0.10`.
- Novelty bonus by TDL: Tdark=1.0, Tbio=0.6, Tchem=0.3, Tclin=0.0.
- Hub penalty: −0.05 for confirmed broad hubs (unless seeded).
- `seed_targets` + GWAS force-includes always appear in output regardless of score.
- `exclude_targets` never appear.
- Warning logged if 20th-place score < 0.25 ("weak signal" for this disease).

---

## LLM Decision Gates

| Gate ID | When | Schema | Critical? |
|---|---|---|---|
| `1.1_efo_disambiguation` | Multiple EFO candidates ≥ 0.6 | `EFODisambiguation` | No |
| `1.4_relevance_prefilter` | Per abstract (local only) | `AbstractRelevance` | No |
| `1.4_extraction` (MAP) | Per chunk | `LiteratureChunkOutput` | No |
| `1.4_merge` (REDUCE) | Per tree-merge group | `LiteratureChunkOutput` | No |
| `1.6_hub_interpretation` | Hub genes detected | `HubInterpretationList` | No |
| `1.8_weight_tuning` | Once per run | `ScoringWeights` | **Yes** (2× self-consistency on small models) |

All gates log to the `decisions` table: `{run_id, phase=1, gate, llm_provider, llm_model, prompt, raw_response, decision_json}`.

---

## Resume Semantics

| Level | Resume mechanism |
|---|---|
| Phase level | `phase_results` row checked before starting — if `completed`, Phase 1 is skipped |
| Literature chunk level | `llm_chunks(run_id, task='phase1_literature_extraction', chunk_index)` checked first — already-`done` chunks skip LLM call |
| All other steps | Stateless, re-run on resume |

---

## Output Contract

```json
{
  "ranked_targets": [
    {
      "rank": 1,
      "ensembl_id": "ENSG00000133703",
      "symbol": "KRAS",
      "aggregate_score": 0.82,
      "modality_hint": "SM",
      "tdl": "Tclin",
      "seeded": false,
      "evidence_trail": {
        "ot": 0.91,
        "literature": 0.78,
        "genetic": 0.85,
        "ppi_eigenvector": 0.72,
        "pathway": 0.90,
        "tractability": 0.80
      }
    }
  ],
  "dark_genome_mode": false,
  "efo_id": "EFO_0002618",
  "disease_label": "pancreatic ductal adenocarcinoma",
  "scoring_weights": { ... },
  "abstract_count": 487,
  "wall_time_s": 312.4
}
```

Written to `phase_results.output_json` and one row per target to the `targets` table.

---

## Known Gaps / Caveats

| Gap | Impact | Status |
|---|---|---|
| STRING uses Ensembl protein IDs, not gene symbols | Network edges may not map cleanly without an ENSP→symbol mapping file | Phase 2 will add proper ID mapping |
| Reactome REST sometimes returns generic pathway matches | Some false-positive pathway assignments | Phase 3 refines modality with deeper pathway analysis |
| No patient cohort expression matrix | GTEx/TCGA reference not wired up (optional in PRD) | Add `patient_cohort.expression_matrix` in RunConfig; decoupleR deferred to Phase 2 |
| OMIM API key pending | Richer disease-specific gene-phenotype scoring unavailable | Covered by local `mim2gene.txt` (0.4 score for all Mendelian genes); upgrade automatic when key arrives |
| LM Studio model name not yet confirmed | `dry_run.py` will fail at LLM provider probe | Set `LMSTUDIO_MODEL` in `.env` to the exact string shown in LM Studio UI |

---

## Acceptance Test

Run against **pancreatic cancer**:
- KRAS, TP53, CDKN2A, SMAD4 must appear in the top 10.
- Top-5 must overlap published pancreatic cancer target lists ≥ 3/5.
- `seed_targets = ["TGFB1"]` → TGFB1 always in output.
- `exclude_targets = ["MUC5B"]` → MUC5B never in output.
- Crash at chunk 47 of 500 → resume completes without re-running chunks 0–46.

---

## File Map

```
src/phases/phase1/
├── __init__.py
├── runner.py                 # Orchestrator — calls all sub-modules in order
├── schemas.py                # Pydantic schemas for all LLM gate outputs
├── disease_normalization.py  # Step 1.1: EFO mapping + LLM disambiguation
├── open_targets.py           # Steps 1.2–1.3: OT associations + Pharos TDL
├── literature_mining.py      # Step 1.4: PubMed/EPMC fetch + map-reduce
├── genetic_evidence.py       # Step 1.5: GWAS (5 TSVs) + OMIM local + DisGeNET
├── ppi_network.py            # Step 1.6: STRING/BioGRID/PrimeKG + centrality
├── pathway_analysis.py       # Step 1.7: Reactome + disease pathway scoring
└── scoring.py                # Step 1.8: Weighted aggregate + ranking

Databases/
├── gwas_catalog/             # 5 year-split association TSVs (669 MB)
└── omim/
    └── mim2gene.txt          # 29,592 OMIM gene entries (downloaded 2026-05-31)
```
