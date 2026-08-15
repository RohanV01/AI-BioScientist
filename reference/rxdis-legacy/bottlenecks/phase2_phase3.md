# Phase 2 + Phase 3 Bottlenecks

**Written:** 2026-06-03T21:30 IST
**Architecture:** Local-first validation pipeline (fpocket + DepMap + AlphaMissense + GTEx parquet)
**Status:** Code complete, 6-target validation passed.

---

## Active bottlenecks (by severity)

### H1 — GTEx gives global mean, not tissue-specific TPM 🔴

**Symptom:** `localization.py` falls back to `gtex_gene_stats.parquet` which has only
`gtex_log_mean_tpm` (across all 54 tissues) and `gtex_pct_expressed`. The
`tissue_of_interest` TPM is set to this global mean, and `tsi` is approximated
as `1 - pct_expressed`. Neither is correct for a tissue-specific drug target decision.

**Impact:**
- `critical_tissue_flag` is always `False` when using the parquet fallback — safety flags
  in heart/brain/kidney won't fire unless the GTEx REST call succeeds.
- `toi_tpm` for a pancreas-enriched gene (e.g., PRSS1) will look the same as a
  ubiquitous gene (e.g., ACTB) — both get their global mean.
- The scoring weight for `expression_score` is diluted because the proxy is noisy.

**Root cause:** The full GTEx parquet (`GTEx_Analysis_2026-05-19_v11_RNASeQCv2.4.3_gene_tpm.parquet`)
has samples as columns, but the sample-attributes metadata file (which maps sample IDs to
tissue names) is not in `Databases/gtex/`. Without it, per-tissue medians can't be computed.

**Fix options (in order of effort):**
1. **Download GTEx sample attributes** (v9 `GTEx_Analysis_v9_Annotations_SampleAttributesDS.txt`, ~10 MB).
   Precompute a `gtex_tissue_medians.parquet` (gene × tissue) once and cache it.
   This is a one-time 5-minute precompute.
2. **Use the GTEx REST API** as primary (already implemented). The REST call fails silently;
   the real fix is to handle transient failures with a retry + timeout budget of ~20s
   rather than falling back immediately.
3. **Use HPA RNA tissue consensus** — `Databases/human_protein_atlas/metadata/rna_tissue_consensus_tissues.tsv`
   exists but is only a tissue list (no expression values). The actual per-gene HPA RNA
   data would need to be downloaded.

**Priority:** High — tissue-of-interest expression and the safety flag are load-bearing
inputs to the validation score and to the LLM narrative gate.

---

### H2 — fpocket runs on every target sequentially, no parallelism 🟡

**Symptom:** Each target in Phase 2 goes through: UniProt lookup → AFDB download → PDB download →
fpocket run → parse. These are sequential within `runner.py`'s `for target in top_targets` loop.
With 20 targets and ~30s per target (PDB download + fpocket), Phase 2 takes ~10 minutes.

**Impact:** Phase 2 wall time is ~10 min for a 20-target run (acceptable for now). With
larger target lists or slow networks it will become the dominant cost.

**Fix:** Parallelise the per-target loop in `runner.py` using `concurrent.futures.ThreadPoolExecutor`
(all the sub-steps are I/O-bound: REST API calls + subprocess). Cap at 4–6 workers to avoid
overwhelming the AlphaFold DB API.

**Note:** DB writes (`upsert_target`) are per-target and need to be serialised or made
batch — this is the one non-thread-safe operation in the loop.

---

### H3 — AlphaMissense `am_high_path_fraction` conflates GoF and LoF variants 🟡

**Symptom:** SMAD4 has `am_high_path_fraction = 0.63` (63% of missense variants are
high-pathogenicity). This looks like a GoF-rich target but SMAD4 is a loss-of-function
tumor suppressor — those 63% of variants are *breaking* the protein, not activating it.
The AM score does not distinguish direction of effect.

**Impact:** The PROTAC scoring uses `high_path_missense ≥ 3` as a GoF boost signal.
For LoF proteins like SMAD4, this is biologically misleading.
Currently mitigated by the Chronos gate (SMAD4 Chronos = −0.06 → PROTAC score near-zero),
but the AM variant boost still inflates the validation score slightly.

**Fix:** Cross-reference AM variants with a directional annotation source:
- **ClinVar** pathogenicity + mechanism (gain-of-function / loss-of-function annotations in the `CLNSIG` and `CLNDN` fields)
- **OncoKB** oncogenicity field distinguishes GoF driver mutations from LoF
- Heuristic proxy: if Chronos > −0.2 in oncology (LoF context), zero out the AM boost

**Priority:** Medium — affects scoring accuracy but the Chronos gate prevents the worst
misclassifications.

---

### H4 — ERBB2 gets SM primary instead of AB when fpocket hasn't run 🟡

**Symptom:** ERBB2 (HER2) has OT tractability = 1.0 (trastuzumab is approved). With the
OT proxy, `max_druggability = 1.0 × 0.7 = 0.70`, which crosses the SM pocket threshold
and makes ERBB2 look like a small-molecule target. The correct primary is AB.

**Root cause:** The OT tractability score is a single scalar that doesn't distinguish *how*
the target is tractable (SM drug vs. approved biologic). ERBB2 scores 1.0 because trastuzumab
exists, not because it has a great SM pocket.

**When it self-corrects:** fpocket running on the actual AFDB structure will find the extracellular
domain has no SM cavity → `max_druggability` drops below 0.5 → `_classify_localization`
correctly routes to AB.

**Interim fix:** When `structure.source == "AFDB"` and `median_plddt < 75` (the kinase domain
of ERBB2 has pLDDT ~74), treat the pocket proxy conservatively: `max_drugg = ot_tract × 0.5`
rather than `× 0.7`. Lower confidence structure → lower druggability confidence.

**Priority:** Low — resolves automatically once fpocket runs. The LLM gate 2.8 will also
catch this edge case if scores are close.

---

### H5 — Validation score weighting not trained, uses hand-tuned constants 🟡

**Symptom:** `scoring.py` uses fixed `_WEIGHTS` dict:
```python
_WEIGHTS = {
    "druggability": 0.25, "genetic": 0.20, "ppi_eigenvector": 0.15,
    "tractability_ot": 0.12, "essentiality_score": 0.12,
    "expression_score": 0.08, "safety_score": 0.08,
}
```
These were set by intuition, not by training against known drug target outcomes.

**Impact:** The rank-ordering within a run is reasonable (KRAS > CDKN2A) but absolute
scores are not calibrated. A score of 0.68 doesn't mean "68th percentile of approved targets."

**Fix:** The PRD specifies XGBoost trained on STRING centralities + DepMap labels with
AUROC ~0.93. The feature set is ready; what's needed is a labelled training set.
`Databases/chembl/chembl_37.db` + OpenTargets tractability scores provide the positive labels
(approved targets = 1). This is a 1-2 day data engineering task.

**Priority:** Medium — the pipeline is scientifically useful now, but calibrated scores
matter for the downstream threshold decisions (which targets proceed to Phase 4/5/6).

---

### L1 — Phase 3 repurposing priority uses OT tractability as clinical-stage proxy 🟢

**Symptom:** `compute_repurposing_priority()` in `rule_engine.py` infers clinical stage
from OT tractability (≥0.9 → HIGH, ≥0.7 → MEDIUM). This is a proxy for the `clinical_stage`
field the PRD specifies from Phase 1 step 1.2b. The Phase 1 output doesn't yet emit a
`clinical_stage` key directly.

**Fix:** Phase 1 step 1.2b should emit `clinical_stage` into the evidence trail using ChEMBL
max phase data. `Databases/chembl/chembl_gene_maxphase.parquet` already exists — Phase 1 just
needs to look up this field and forward it.

**Priority:** Low — OT tractability is a reasonable proxy for now.
