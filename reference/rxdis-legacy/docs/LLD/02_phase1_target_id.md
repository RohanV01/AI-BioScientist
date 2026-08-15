# LLD-02: Phase 1 — Target Identification (Tabular PU-Learning)

**Source:** `src/phases/phase1/`  
**PRD:** `docs/PRD_phase1_target_id.md`  
**Scientific Protocol:** `Scientific Protocol/phase1_target_identification.md`  
**Celery queue:** `cpu`  
**Input:** Phase 0 output + `RunConfig`  
**Output:** `phase1_output: dict` → `phase_results.output_json` (phase=1) + `targets` rows

---

## 1. Module Structure

```
src/phases/phase1/
├── runner.py              — orchestrates all steps, writes DB
├── disease_normalization.py — EFO resolution, MONDO/DOiD cross-refs
├── matrix.py              — feature matrix assembly (Step 1.2)
├── ppi_network.py         — STRING graph + Node2Vec/SVD embedding (Step 1.3)
├── pu_model.py            — bagging-PU or two-step PU learning (Step 1.4)
├── scoring.py             — SHAP attributions (Step 1.5)
├── causal_filter.py       — DoRothEA TF master-regulator (Step 1.6)
├── genetic_evidence.py    — GWAS Catalog, OMIM lookups (supplemental)
├── open_targets.py        — Optional OT GraphQL pull for tractability hint
├── literature_mining.py   — DEPRECATED (kept for historical reference only)
├── pathway_analysis.py    — supplemental pathway enrichment
└── schemas.py             — Pydantic models for phase outputs
```

---

## 2. Entry Point

```python
# src/phases/phase1/runner.py

def run_phase1(
    run_id: str,
    config: RunConfig,
    db,
    phase0_output: dict,
) -> dict:
    """
    Returns ranked_targets output dict.
    Writes phase_results(phase=1) and one targets row per ranked gene.
    """
```

### Execution sequence

```
1.1  disease_normalization.resolve_efo(config)         → efo_id, disease_label
1.2  matrix.build_feature_matrix(config)               → DataFrame (20k genes × ~561 cols)
1.3  ppi_network.get_node2vec_embedding(config)        → loaded from cache or recomputed
1.4  pu_model.run_pu_learning(matrix, config)          → scored_genes: Dict[str, float]
1.5  scoring.compute_shap(model, matrix, top_hits)     → shap_values: Dict[str, List[dict]]
1.6  causal_filter.run_dorothea(top_hits, config)      → tf_flags: Dict[str, TFInfo]
1.7  _rank_and_persist(scored_genes, shap_values, tf_flags, config, db)
```

---

## 3. Step 1.1 — Disease Resolution (`disease_normalization.py`)

```python
def resolve_efo(config: RunConfig) -> Tuple[str, str]:
    """
    Returns (efo_id, disease_label).
    1. If config.disease_efo_id set → use directly (required since 2026-06-07).
    2. Else query Open Targets search API → list of {id, score, label}.
    3. If single result ≥0.8 → use it.
    4. If multiple results ≥0.6 → LLM gate 1.1_efo_disambiguation.
    5. Fallback: top result regardless of score, with warning.
    """

def _efo_disambiguation_gate(candidates: List[dict], config: RunConfig) -> str:
    """LLM gate: selects correct EFO from ambiguous list."""
    # Prompt: "Disease: {disease_name}. Candidates: {list of id+label+score}"
    # Output schema: {"selected_efo_id": "EFO_...", "reason": "..."}
    # Fallback: return candidates[0]["id"]
```

---

## 4. Step 1.2 — Feature Matrix Assembly (`matrix.py`)

### `build_feature_matrix(config: RunConfig) -> pd.DataFrame`

Returns `float32` DataFrame with index = HGNC symbol, columns = feature blocks below.

**Gene universe:** ~20,000 protein-coding genes from HGNC canonical list. Rows missing from a data source → `NaN`, imputed as 0.0 or feature-mean.

#### Feature blocks

| Block | Columns | Source file | Build method |
|---|---|---|---|
| Node2Vec embedding | 512 cols (`node2vec_0` … `node2vec_511`) | `Databases/string/string_node2vec_512.parquet` | Step 1.3 (loaded) |
| DepMap essentiality | `chronos_median`, `chronos_selective_frac` | `Databases/depmap/CRISPRGeneEffect.csv` | Chunked CSV read |
| GTEx expression | `gtex_{tissue_of_interest}`, `gtex_mean`, `gtex_cv` | `Databases/gtex/*_gene_tpm.parquet` | Parquet read, tissue column select |
| AlphaMissense constraint | `am_mean_score`, `am_high_path_frac` | `Databases/alphamissense/AlphaMissense_hg38.tsv` | Chunked TSV read, ENSG→symbol |
| STRING network scalars | `string_degree`, `string_eigenvector` | reused from Step 1.3 graph | `nx.eigenvector_centrality_numpy` |
| GWAS / OMIM (optional) | `gwas_catalog_hits`, `omim_phenotypes` | `genetic_evidence.py` | REST API if keys present |
| Harmonizome (optional) | variable, per dataset | `Databases/harmonizome/` | Parquet, impute NaN |

#### Memory discipline

```python
def _load_depmap_chunked(path: str, gene_universe: Set[str]) -> pd.DataFrame:
    """
    Reads CSV in 5000-row chunks. Keeps only rows in gene_universe.
    dtype: float32. Drops chunk reference immediately after accumulation.
    Peak RAM contribution: ~200 MB.
    """

def _load_string_scalars(graph: nx.Graph) -> pd.DataFrame:
    """
    degree = nx.degree dict. eigenvector_centrality via numpy eigensolver.
    float32. Only called once per session (cached in module-level dict).
    """
```

**Merge key:** All sources mapped to HGNC symbol via a pre-built ID map:
```python
# Built once and cached: Databases/id_maps/hgnc_map.parquet
# Columns: hgnc_symbol, ensembl_gene_id, uniprot_id, string_ensp_id
```

---

## 5. Step 1.3 — Node2Vec Embedding (`ppi_network.py`)

```python
EMBEDDING_CACHE = "Databases/string/string_node2vec_512.parquet"
CONFIDENCE_FLOOR_DEFAULT = 700

def get_node2vec_embedding(config: RunConfig) -> pd.DataFrame:
    """
    Returns DataFrame(index=hgnc_symbol, cols=node2vec_0..511, dtype=float32).
    Loads from cache if present, otherwise triggers recompute.
    Cache key: parquet filename encodes confidence_floor.
    """

def _build_string_graph(confidence_min: int = 700) -> nx.Graph:
    """
    Reads 9606.protein.links.detailed.v12.0.txt (868 MB).
    Chunked read: 50K lines at a time.
    Filters: combined_score >= confidence_min.
    Maps ENSP → HGNC symbol via hgnc_map.parquet.
    Returns undirected weighted graph. Edge weight = combined_score / 1000.
    """

def _compute_netmf_embedding(graph: nx.Graph, n_components: int = 512,
                              random_state: int = 42) -> np.ndarray:
    """
    NetMF / SVD spectral embedding (gensim-free, Python 3.14 native).
    Steps:
      1. Build symmetric normalized adjacency A_hat = D^-0.5 A D^-0.5 (scipy.sparse)
      2. Compute PPMI approximation: log(vol * (A_hat^T + A_hat) / 2b) - log(1)
         where vol = sum of all weights, b = context window size (default 10)
      3. TruncatedSVD(n_components=512, random_state=42).fit_transform(PPMI)
    Returns ndarray shape (n_nodes, 512).
    Peak RAM: ~4 GB for full STRING graph. float32 throughout.
    """
```

**One-time precompute cost:** ~20–40 min on CPU. Cached permanently. Regenerated only if `string_confidence_min` changes in config.

---

## 6. Step 1.4 — PU Learning Core (`pu_model.py`)

```python
def run_pu_learning(
    feature_matrix: pd.DataFrame,
    config: RunConfig,
) -> Dict[str, float]:
    """
    Returns dict: hgnc_symbol → calibrated P(target | features).
    """
```

### Bagging-PU (Mordelet–Vert) — default method

```python
def _bagging_pu(
    X: np.ndarray,        # (n_genes, n_features) float32
    positive_mask: np.ndarray,  # bool, shape (n_genes,)
    n_bags: int,          # config.pu_n_bags, default 30
    base_estimator: str,  # "lightgbm" | "xgboost"
    random_state: int = 42,
) -> np.ndarray:
    """
    Algorithm:
      For each bag b in range(n_bags):
        1. Sample |P| negatives without replacement from unlabeled set U
           (where |P| = number of positives, typically 5–10)
        2. Fit base_estimator on P (label=1) ∪ sampled_negatives (label=0)
        3. Predict proba on all 20K genes
      Final score = mean(proba) across all bags
    Returns calibrated_score shape (n_genes,).
    random_state used for numpy seeding + LightGBM/XGBoost seed.
    """
```

### Two-step PU — alternative

```python
def _two_step_pu(X, positive_mask, base_estimator, random_state=42):
    """
    Step 1 (spy method): Label 15% of P as "spies" → treat as unlabeled.
                         Train initial classifier. Threshold on spy scores.
    Step 2: Reliable negatives = U with score below spy threshold.
            Retrain on P + reliable_negatives.
    """
```

### Base estimator setup

```python
def _make_estimator(estimator_name: str, random_state: int):
    if estimator_name == "lightgbm":
        import lightgbm as lgb
        return lgb.LGBMClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            num_leaves=63, random_state=random_state,
            verbose=-1, n_jobs=-1
        )
    elif estimator_name == "xgboost":
        import xgboost as xgb
        return xgb.XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            use_label_encoder=False, eval_metric="logloss",
            random_state=random_state, n_jobs=-1
        )
```

### AUROC (leave-one-out cross-validation)

```python
def _loo_auroc(X, positive_mask, estimator_name, n_bags, random_state) -> float:
    """
    For each positive gene g:
      Remove g from positive set → treat as unlabeled
      Run bagging-PU on remaining positives
      Check if g ends up in top 5% of all genes → hit
    AUROC approximation = fraction of positives recovered / expected by chance
    Reported in output but not used to gate the run.
    """
```

---

## 7. Step 1.5 — SHAP Attributions (`scoring.py`)

```python
def compute_shap(
    model,                    # trained LightGBM/XGBoost from last bag
    feature_matrix: pd.DataFrame,
    top_indices: np.ndarray,  # indices of top-ranked genes
    feature_names: List[str],
) -> Dict[str, List[dict]]:
    """
    Uses shap.TreeExplainer on final bag model.
    For each top gene: top 10 feature contributions sorted by |shap_value|.
    Returns: {symbol: [{feature, value, shap_contribution}]}

    Note: uses the last bag's model (representative). Full ensemble SHAP
    would multiply runtime by n_bags.
    """
```

---

## 8. Step 1.6 — Causal Filter (`causal_filter.py`)

```python
def run_dorothea(
    top_hits: List[str],         # HGNC symbols
    config: RunConfig,
    expression_matrix: Optional[pd.DataFrame] = None,  # from patient_cohort
) -> Dict[str, TFInfo]:
    """
    Returns dict: symbol → TFInfo

    Mode A (no expression_matrix):
      Load DoRothEA regulons via decoupler/omnipath (confidence A/B/C).
      Flag genes that are high-confidence TFs with regulon_size >= 10.
      is_master_regulator = True if A/B confidence and regulon_size >= 20.

    Mode B (expression_matrix provided):
      Run decoupler.run_ulm() or decoupler.run_mlm() to compute TF activity.
      Returns NES (normalised enrichment score) per TF.
    """

@dataclass
class TFInfo:
    is_tf: bool
    confidence: Optional[str]     # "A", "B", "C", None
    regulon_size: int
    is_master_regulator: bool
    dorothea_activity: float      # NES if Mode B, 0.0 if Mode A
```

**Fallback:** If `decoupler`/`omnipath` fetch fails → load static HGNC TF list from a bundled CSV, set `confidence=None`, `regulon_size=0`.

**LLM gate `1.6_master_regulator`** (optional, only when LLM enabled and TFs in top hits):
```
Prompt: "Target {symbol} is a transcription factor regulating {regulon_size} genes.
Top regulated genes: {regulon[:10]}. Explain in 2 sentences why this is a 
master regulatory switch for {disease_label}."
Output: {"summary": "..."}
Fallback: summary = "TF with {regulon_size} downstream targets."
```

---

## 9. Step 1.7 — Rank, Select, Persist

```python
def _rank_and_persist(
    scored_genes: Dict[str, float],    # symbol → PU probability
    shap_values: Dict[str, List[dict]],
    tf_flags: Dict[str, TFInfo],
    config: RunConfig,
    db,
    efo_id: str,
    disease_label: str,
    model_meta: dict,
) -> dict:
    """
    Final score = pu_probability * (1 + 0.05 * is_master_regulator)
    Select top target_count_max genes.
    known_positives/seed_targets always included (seeded=True), score clamped to 1.0.
    exclude_targets removed.

    For each selected gene:
      - Fetch tdl from HGNC (Tclin/Tchem/Tbio/Tdark) if available
      - Compute pu_percentile (percentile rank in full 20K universe)
      - Build evidence_trail dict (see output contract)
      - Call db.upsert_target(...)
    """
```

---

## 10. Output JSON Contract

```json
{
  "ranked_targets": [
    {
      "rank": 1,
      "ensembl_id": "ENSG00000133703",
      "symbol": "KRAS",
      "aggregate_score": 0.94,
      "modality_hint": "SM",
      "tdl": "Tclin",
      "seeded": true,
      "evidence_trail": {
        "xgb_probability": 0.94,
        "pu_percentile": 0.999,
        "dorothea_activity": 0.0,
        "is_master_regulator": false,
        "regulon_size": 0,
        "essentiality_chronos": -0.71,
        "string_degree": 118,
        "shap_top": [
          {"feature": "node2vec_dim_137", "value": 0.09},
          {"feature": "gtex_pancreas", "value": 0.06}
        ],
        "tractability": 1.0,
        "genetic": 0.0,
        "ppi_eigenvector": 0.99
      }
    }
  ],
  "efo_id": "EFO_0002618",
  "disease_label": "pancreatic carcinoma",
  "model": {
    "method": "bagging-PU",
    "estimator": "lightgbm",
    "auroc_loo": 0.91,
    "n_positives": 5,
    "n_genes": 19990,
    "n_bags": 30
  },
  "causal_filter": {"n_master_regulators": 3},
  "feature_matrix": {"rows": 19990, "cols": 561, "peak_ram_mb": 1840},
  "wall_time_s": 612
}
```

### Phase-2 compatibility keys (do not drop)

`evidence_trail.tractability`, `.genetic`, `.ppi_eigenvector` — consumed by `phase2/runner.py:82` and `phase2/scoring.py:60-61`. Populated from optional Open Targets pull (`open_targets.py`), GWAS/OMIM (`genetic_evidence.py`), and STRING eigenvector.

---

## 11. DB Writes

```
phase_results: phase=1, running → completed
               output_json = full ranked_targets dict
targets: one row per selected gene
         columns: run_id, symbol, rank, ensembl_id, aggregate_score,
                  tdl, seeded, evidence_trail
decisions: gate="1.1_efo_disambiguation" (if ran)
           gate="1.6_master_regulator"   (if ran, per TF target)
compute_log: step="string_precompute", wall_time_s (only if recomputed)
             step="pu_learning", wall_time_s
```

---

## 12. Failure / Recovery

| Failure | Recovery |
|---|---|
| Node2Vec cache missing | Trigger `_build_string_graph` + `_compute_netmf_embedding`; log "one-time precompute" |
| `< 5 known_positives` | Warn; union with `seed_targets`; report `"reduced_confidence": true` in model meta |
| Harmonizome blocks absent | Impute `NaN → 0.0`; feature columns still present, all zeros |
| DoRothEA / omnipath fetch fails | Fall back to static TF list, `confidence=None` |
| ID map gaps (gene not resolvable) | Log count of unmapped genes; skip from universe |
| Peak RAM exceeds available | Reduce `node2vec_dim` (512 → 256 → 128); increase chunk size threshold |
| EFO resolution fails | Proceed with `efo_id = None`; no OT annotation; log warning |
| All known_positives absent from universe | Hard error — user must fix gene names |

---

## 13. Performance Characteristics

| Step | Typical time | Peak RAM |
|---|---|---|
| Node2Vec (first time) | 20–40 min | ~4 GB |
| Node2Vec (cached) | 2–5 s | ~200 MB |
| Feature matrix assembly | 3–8 min | ~2–4 GB |
| Bagging-PU (30 bags, LightGBM) | 5–15 min | ~3–6 GB |
| SHAP | 1–3 min | ~1 GB |
| DoRothEA | 30–120 s (first fetch) | ~200 MB |
| **Total (cold)** | **~30–70 min** | **< 10 GB** |
| **Total (warm cache)** | **~10–20 min** | **< 6 GB** |
