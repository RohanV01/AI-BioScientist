# Phase 1 Bottlenecks — Current Profile

**Last updated:** 2026-05-31 (post-DISEASES integration + AlphaMissense + all bug fixes)
**Architecture:** Tabular PU-Learning (NLP pipeline retired)
**Status:** All critical blockers resolved. Peak RAM 300 MB; no GPU used.

---

## Active bottlenecks (ranked by impact)

### H1 — Genetic evidence coverage for rare/obscure diseases 🟡
**Severity:** Medium (affects score quality, not correctness)
**Symptom:** `genetic` scores are 0.0 for most genes on rare diseases where Jensen DISEASES
and GWAS Catalog have thin coverage. PU probability still ranks correctly.
**Root cause:** All three genetic sources (GWAS, OMIM, DISEASES) are biased toward
well-studied diseases. Jensen DISEASES textmining has 94 genes for pancreatic cancer,
10,260 after name-fuzzy matching; for truly rare diseases coverage may drop to <50 genes.
**Mitigation:** OT `genetic_association` score blended in (step 1.6) provides non-zero
signal even when local files miss. ClinVar `variant_summary.txt.gz` (439 MB) is the next
logical addition — adds variant-level pathogenicity evidence aggregated to gene level.

### H2 — GWAS Catalog local file scan: ~5s per run 🟢
**Severity:** Low — acceptable at 5 diseases/day
**Description:** Scans 669 MB of year-split TSVs (50k-row pandas chunks). Memory-safe.
**Improvement path:** Pre-index to a disease→gene parquet keyed by EFO+MONDO+name prefix.
10s upfront build → <0.1s subsequent lookups. Worth doing when disease library > 20.

### H3 — Open Targets API latency: ~3s per run 🟢
**Severity:** Low — acceptable
**Description:** 3–6 paginated GraphQL pages (300 targets) + 1 xrefs call. ~3s.
**Handled:** `_ot_post_with_retry` (4 attempts, exponential back-off on 5xx).

---

## Resolved bottlenecks

| ID | Date | Description |
|----|------|-------------|
| **B-HANG** | 2026-05-31 | Phase 1 hung >250s in ranking loop. SHAP map (19k keys) stored in `DataFrame.attrs`; pandas deep-copies attrs onto every row Series created by `iterrows()` → O(n²). **Fix:** keep attrs scalar-only, return shap_map separately, switch to `itertuples`. Now 8ms. |
| **B12** | 2026-05-31 | `targets` upsert on_conflict had no matching DB constraint → 0 targets persisted. **Fix:** `clear_targets(run_id)` + plain `insert()` in `run_state.py`. No DDL migration needed. |
| **B-GWAS** | 2026-05-31 | GWAS local parse returned 0 rows. Code searched `EFO:0002618` (colon) but file URIs use `EFO_0002618` (underscore). Also missed MONDO IDs. **Fix:** search raw efo_id + numeric suffix + disease name prefix. Now 124 genes for pancreatic cancer. |
| **B-DISGENET** | 2026-05-31 | DisGeNET migrated to new domain + API v1; free tier = 10 requests/day — impractical for development. **Fix:** replaced with Jensen Lab DISEASES (3 local TSVs, 9.2 MB, no rate limits, equivalent coverage). |
| **B-AM-MAP** | 2026-05-31 | AlphaMissense block skipped — no UniProt→symbol map. **Fix:** downloaded HGNC complete set (1.1 MB). Maps 20,164 accessions. One-time 37s stream → 0.4 MB cache. |
| **B-RE** | 2026-05-31 | Accidental removal of `import re` when cleaning up `import subprocess` → NameError in DepMap column cleanup. **Fix:** re-added `import re`. |
| **B-GWAS-IDX** | 2026-05-31 | `pd.Series([False]*len(chunk))` — unaligned index vs chunk's continuing RangeIndex → pandas alignment warning + silent misses. **Fix:** `pd.Series(False, index=chunk.index)`. |

---

## Performance reference (warm run, 2026-05-31)

```
Step                         Time    Memory
─────────────────────────────────────────────────
1.1  Disease normalization    <1s     —        (EFO ID provided → skipped)
1.2  Open Targets pull        ~3s     —        (tractability + genetic_assoc + DOIDs)
1.3  Feature matrix (518-col) ~7s     42 MB    (GTEx + AlphaMissense from parquet cache)
1.4  PU learning (20 bags)    ~3s     250 MB   (LightGBM, all CPU cores)
1.5  DoRothEA annotation      <1s     —        (32k-edge cached parquet)
1.6  Genetic evidence         ~5s     —        (GWAS 5×TSV scan + DISEASES 3×TSV + OT-GA)
     Jensen DISEASES alone:   <1s     —        (9.2 MB, line-scan, 10k gene matches)
1.7  PPI proxy                <1s     —        (single column lookup)
1.8  Rank + DB persist        ~3s     —        (clear + 20 inserts)
─────────────────────────────────────────────────
     TOTAL (warm)            ~55s    ~300 MB
```

**Cold first-run additions (one-time only):**
- GTEx stream: +52s → cache `gtex_gene_stats.parquet`
- AlphaMissense stream: +37s → cache `am_gene_stats.parquet`

Hardware: i5-12th Gen, 16 GB RAM, RTX 3050 6 GB (GPU not used in Phase 1).
RAM headroom: 300 MB used of 16 GB available. No pressure.
