# Phase 1 Bottlenecks — Current Profile

**Last updated:** 2026-06-01
**Architecture:** Biological Fingerprint PU-Learning (v2)
**Status:** Production-ready. Peak RAM ~300 MB; no GPU; warm run ~50s (pancreatic).

---

## Active bottlenecks (by severity)

### H1 — `primekg_disease_degree` dominates feature importance 🔴

**Symptom:** Feature gain: primekg_disease_degree=328 vs. string_exp=83 for pancreatic cancer; 1000 vs 110 for breast cancer. Every gene's top SHAP feature is `primekg_disease_degree`. Model is primarily learning "how broadly disease-connected is this gene" rather than disease-specific biology.

**Root cause:** The 15-80 OT-confirmed positives happen to be well-studied genes with high PrimeKG disease connectivity (TP53=257 disease nodes, KRAS=200). The model correctly identifies this as discriminating but it captures "general disease gene hub" rather than "relevant to this specific disease."

**Impact:** Novel hypotheses surfaced by the model are biologically plausible general cancer/disease genes (BLM, FANCD2, MSH2 for pancreatic cancer) rather than specifically pancreatic-driven candidates. False positives like ESR1 for PDAC appear — correctly filtered by Phase 2, but ideally screened earlier.

**Mitigation in place:** The two-score output separates `pu_bio_score` (which drives this) from `ot_genetic_assoc` (disease-specific). Phase 2 receives both and uses `ot_genetic_assoc` as a disease-specificity filter.

**Next steps:**
- Download COSMIC Cancer Gene Census (1 MB, free registration). Adding `cosmic_tier` (0/1/2) as a feature would give the model a curated "confirmed cancer driver" signal that is more cancer-specific than PrimeKG disease degree.
- Compute disease-specific PrimeKG degree: count edges only to disease nodes in the same ontological neighbourhood as the query disease. This is a per-run precompute but would be disease-specific.
- Alternatively: cap `primekg_disease_degree` importance via monotone constraints in LightGBM (force a ceiling on the feature's split gain fraction).

---

### H2 — LOO-AUROC evaluation time scales O(n_positives²) 🟡

**Symptom:** Breast cancer with 78 positives took 112s for PU learning (vs 30s for pancreatic with 31). Parkinson's with 71 positives took 116s.

**Root cause:** LOO-AUROC holds out each positive once, retrains a mini-ensemble (`n_bags//3` bags), and scores all 19,699 genes. With 78 positives: 78 × 10 bags × 19,699 genes = 15M LightGBM predictions just for evaluation.

**Impact:** Acceptable for single runs. Will become a bottleneck when running batch disease sweeps or hyperparameter tuning.

**Mitigation:** Reduce `n_bags//3` to `max(1, n_bags//5)` for LOO — reduces evaluation cost by ~40% with minimal AUROC estimate noise. Or move LOO to a subsample: randomly hold out 10% of positives per fold rather than 1. Add a `fast_auroc=True` flag to `run_pu_learning()`.

---

### H3 — OMIM and ChEMBL near-zero feature importance 🟡

**Symptom:** `is_mendelian` gain = 0.2–3.2, `chembl_max_phase` gain = 0.2–9 across all three diseases. These features are in the matrix but not contributing meaningfully.

**Root cause:**
- `is_mendelian` (OMIM): 16,415 of 19,699 genes are flagged as Mendelian (83% base rate). Zero discriminating power.
- `chembl_max_phase`: 1,542 human targets have ChEMBL data. Most positives have approved drugs, but so do many unlabelled genes. Weak signal.

**Impact:** These features take space in the matrix and introduce noise. No measurable performance benefit currently.

**Next steps:**
- `is_mendelian`: Replace with disease-specific OMIM entry (genemap2.txt maps gene→disease). This would give a binary "is this gene in OMIM for THIS disease" signal rather than "is this gene Mendelian for any disease." Requires OMIM API key or downloading genemap2.txt.
- `chembl_max_phase`: Supplement with COSMIC (cancer gene census) for oncology diseases, and gnomAD pLI/LOEUF for constraint. These have much higher discriminating power.

---

### H4 — Rare disease positive set collapse 🟡

**Symptom:** For rare diseases (e.g., Wilson disease, Niemann-Pick), OT-GA ≥ 0.5 may yield fewer than 5 genes, causing the positive set to be dominated by user seeds.

**Root cause:** OT genetic association scores are computed from GWAS, somatic mutation studies, animal models, and literature — rare diseases have sparse coverage in all four.

**Impact:** Returns to the 5-positive regime where the model has insufficient training signal and collapses to a single-feature discriminator.

**Mitigation:** Add a fallback: if OT-GA ≥ 0.5 yields < 10 genes, lower threshold to 0.3 and log a warning. Also supplement with ClinVar pathogenic variant genes for the disease — these are often available for rare Mendelian diseases.

---

### H5 — OT API latency and rate limiting 🟢

**Symptom:** ~5s for OT GraphQL pull (300 targets) + 2 xref calls. Occasional 5xx errors handled by `_ot_post_with_retry` (4 attempts, exponential backoff).

**Impact:** Acceptable for single runs. For batch sweeps across 50+ diseases simultaneously, the OT API gateway may throttle.

**Mitigation:** Add a local OT association cache keyed by `(efo_id, date)`. Refresh weekly or on-demand. The OT public release is monthly — caching per-disease for 30 days is safe.

---

## Resolved (historical log)

| ID | Date | Description | Fix |
|----|------|-------------|-----|
| B-EMB-BIAS | 2026-06-01 | STRING 512-d Node2Vec embedding encoded textmining (r=0.662). All SHAP was `emb_*`; 11/16 features had zero gain. | Replaced embedding with 6 channel-specific + structural features. |
| B-OT-GA-COLLAPSE | 2026-06-01 | With 5 positives and OT-GA in matrix, first tree split perfectly separated all positives. Features essentiality/expression/constraint had zero gain. | Removed OT-GA from training features; used it to expand positive set to 15-80 genes. |
| B-AUROC-INFLATION | 2026-06-01 | LOO-AUROC 0.999 was measuring whether OT-GA-positive genes outrank OT-GA-zero genes — trivially easy. | Two-score output; AUROC now 0.755–0.915 (honest difficulty). |
| B-JENSEN-WILDCARD | 2026-06-01 | `dis_name in disease_key` matched any short string (e.g. "cancer") inside disease name → 10,228 false positives for pancreatic cancer. | Replaced with disease-specific word matching: extract words > 4 chars not in generic list. |
| B-GWAS-MONDO | 2026-06-01 | GWAS Catalog uses MONDO IDs (MONDO_0005192) not EFO IDs for most cancers; EFO search returned 0 hits. | Fetch MONDO xrefs from OT; search both EFO and MONDO in MAPPED_TRAIT_URI. |
| B-OMIM-WEIGHT | 2026-06-01 | OMIM score 0.4 for all Mendelian genes was dominating when disease-specific sources failed (pancreatic genetic=0.320 flat). | Lowered to 0.1; OT-GA now dominates for confirmed disease genes. |
| B-PPI-FLAT | 2026-06-01 | ppi_eigenvector from emb_0 had range 0.3814–0.3840 (near-zero variance). | Replaced with STRING degree centrality (combined_score ≥ 700); TP53=1532, FANCE=121. |
| B-SHAP-OPACITY | 2026-06-01 | SHAP showed 100% `emb_*` entries; biological features invisible. | New architecture: all 14 features interpretable; top-8 shown in evidence trail. |
| B-TDL-UNKNOWN | 2026-06-01 | Pharos `targets(targets: $symbols)` schema rejected; all TDL = "unknown". | Switched to GraphQL aliases: `g0: target(q: {sym: "KRAS"}) { sym tdl }`. 20/20 resolved. |
| B-HANG | 2026-05-31 | Phase 1 hung >250s: DataFrame.attrs SHAP map deep-copied by iterrows → O(n²). | Keep attrs scalar-only, return shap_map separately, use itertuples. Now 8ms. |
| B12 | 2026-05-31 | `targets` upsert ON CONFLICT failed → 0 targets persisted. | `clear_targets(run_id)` + plain `insert()`. |
| B-GWAS-IDX | 2026-05-31 | `pd.Series([False]*len(chunk))` misaligned index. | `pd.Series(False, index=chunk.index)`. |

---

## Performance reference

```
WARM RUN — Pancreatic cancer (~31 positives, cached databases)
───────────────────────────────────────────────────────────────────
Step                                 Time     Memory
1.1  EFO provided (skip)              <1s      —
1.2  OT pull (300 targets, 3 pages)   ~5s      —
1.2b Positive set expansion            <1s      —
1.3  14-feature matrix (all parquet)  ~3s     2.3 MB
1.4  PU learning (20 bags, 31 pos)   ~30s    ~150 MB
1.5  DoRothEA annotation              <1s      —
1.6  Genetic evidence (GWAS+DISEASES) ~5s      —
1.7  STRING degree (cached)           <1s      —
1.7b Pharos TDL (20 targets)          ~2s      —
1.8  Rank + persist 20 targets        ~3s      —
───────────────────────────────────────────────────────────────────
     TOTAL                           ~50s    ~300 MB peak

WARM RUN — Breast cancer (~77 positives)
1.4  PU learning (20 bags, 77 pos)  ~100s    ~150 MB
     TOTAL                          ~120s

COLD FIRST-RUN (one-time only, all databases fresh)
GTEx parquet streaming               +52s
AlphaMissense streaming              +37s
STRING channel degrees               +20s
PrimeKG degrees                      +15s
BioGRID physical degree               +5s
ChEMBL sqlite query                   +2s
     FIRST-RUN TOTAL                ~170s   (then all cached)
```

Hardware: Intel i5-12th Gen, 16 GB RAM, RTX 3050 (GPU not used in Phase 1).
