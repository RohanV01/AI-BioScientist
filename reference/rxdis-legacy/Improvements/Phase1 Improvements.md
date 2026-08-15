# Phase 1 — Target ID: Rationale, Gaps & Improvement Scope

## Scientific Rationale

Phase 1 answers: **"Which genes are likely causal drivers of this disease, ranked by multi-omic confidence?"**

The approach is a **PU (Positive-Unlabeled) learning** pipeline — it treats known disease genes as positives and all other human genes as unlabeled (not negative). The model learns a 14-feature biological fingerprint of known disease genes and scores the entire proteome.

**Why this approach over simpler ranking:**
- Disease gene databases (OMIM, GWAS) are heavily biased toward well-studied genes. A straight OT/GWAS score would just re-rank what pharma already knows.
- PU learning corrects for this: it can find *novel* targets that look biologically like known positives but haven't been validated yet.
- The 14 features are disease-agnostic (essentiality, expression, network centrality, AlphaMissense, ChEMBL precedent) — so the model generalizes across disease areas.

**The two output scores:**

| Score | What it means |
|---|---|
| **PU Score** (0–1) | Probability the gene is a true positive per the PU model — a biological similarity score |
| **Val. Score** | Phase 2 druggability validation score — pockets, expression, essentiality weighted — only available after Phase 2 runs |

**TDL (Target Development Level)** from Pharos adds a clinical precedent axis: Tdark → Tbio → Tchem → Tclin.

---

## What Information Is Incomplete / Missing from the UI

### A. Data computed but never shown

These fields are in `evidence_trail` JSONB in the DB right now but have no UI representation:

| Field | What it is | Why it matters |
|---|---|---|
| `dorothea_confidence` | Letter grade (A/B/C) for master-regulator status | A-grade regulators are strong mechanistic drivers |
| `regulon_size` | # genes this TF controls | Bigger regulon = broader disease relevance |
| `selectivity` | Fraction of cancer cell lines where gene is essential | High selectivity = cancer-specific target, low off-target risk |
| `am_pathogenicity` | AlphaMissense mean pathogenicity across all missense variants | Functional constraint — high = structurally sensitive |
| `am_high_path_frac` | Fraction of missense variants called pathogenic | Mutation hotspot indicator |
| `ppi_eigenvector` | STRING network centrality | Hub genes are harder to drug but more disease-central |
| `genetic` | Merged GWAS + OMIM + DISEASES score | Direct genetic-disease link — high = human-validated |
| `pu_percentile` | Rank percentile within the scored proteome | More meaningful than raw score for novelty assessment |

### B. Visualization stubs (placeholder UI, no data behind them)

1. **Pathway Enrichment card** — "[Visualization Loading…]"  
   The backend never runs pathway enrichment (GSEA/ORA). No data exists.

2. **Expression Heatmap card** — "[Visualization Loading…]"  
   GTEx expression is stored as a single scalar (`log1p(mean TPM)`). No tissue-level breakdown is computed or stored.

3. **3D Protein Viewer** (Inspector → Viewer tab) — "Integrate NGL Viewer"  
   H-Bonds (12), Hydrophobic (28), Pocket Vol (450 Å³), Druggability (0.82) are **all hardcoded constants**, not real data.

4. **Evidence Logs** (Inspector → Logs tab) — Hardcoded dummy timestamps  
   Not wired to actual pipeline step logs. Shows a fake timeline.

### C. AI rationale text is a static template

The "Why?" inspector shows a paragraph that mentions "expression" and "toxicity" but is a hardcoded template string — it doesn't actually use the SHAP values to generate the explanation.

### D. Val. Score column is always "—" during Phase 1

This is correct behavior (Phase 2 fills it), but there's no tooltip explaining why it's empty.

### E. GTEx expression bar represents only mean TPM

A single bar can't distinguish "expressed everywhere" from "expressed only in tumor tissue" — which is the scientifically relevant question.

---

## Scope of Improvement (Prioritized)

### Tier 1 — Low effort, high signal (data already exists in DB)

1. **Surface dorothea_confidence + regulon_size in Inspector SHAP tab**  
   Add a "Master Regulator" badge (A/B/C) and regulon count alongside SHAP bars.

2. **Show selectivity score** as a column or Inspector stat card  
   Rename/reframe "GTEx Expression" bar to also show selectivity side-by-side.

3. **Show genetic score** as a column (between PU Score and TDL)  
   This is the *human validation* signal — should be front-and-center.

4. **Replace hardcoded AI rationale** with a template that actually reads `shap_top[0..2]` and `is_master_regulator` + `dorothea_confidence` to generate a meaningful per-target explanation.

5. **Add tooltip on Val. Score "—"** explaining it populates after Phase 2.

6. **Show pu_percentile in Inspector** — "Top 0.4% of 19,847 genes scored"  
   Contextualizes the raw 0.875 PU score meaningfully.

### Tier 2 — Medium effort, meaningful completeness

7. **Wire Evidence Logs to actual DB step data**  
   The orchestrator already logs phase steps — surface real timestamps and step names.

8. **Replace stub Druggability/H-Bond stats in Viewer tab** with Phase 2 pocket data  
   Phase 2 computes real pocket volume and druggability scores stored in `evidence_trail`. These could render in the Phase 1 view when Phase 2 has already completed.

9. **AlphaMissense feature card** — show `am_pathogenicity` + `am_high_path_frac` as a "Mutational Constraint" stat in Inspector.

### Tier 3 — Higher effort, requires new backend computation

10. **Tissue expression heatmap** — requires GTEx per-tissue breakdown stored per target (currently only mean is stored). Backend change needed in `src/phases/phase1/matrix.py`.

11. **Pathway Enrichment** — requires a GSEA/ORA step (e.g. using `gseapy`) on the top-N targets. New Phase 1 pipeline step needed.

12. **Real AlphaFold 3D viewer** — NGL Viewer integration in frontend; requires fetching PDB/mmCIF from AlphaFold DB per target using UniProt/Ensembl ID.

---

## Recommended First Pass

Start with **Tier 1 items 1–6**: zero backend changes required, data already sits in `evidence_trail` JSONB, and the result is a "Why?" inspector that actually explains the science per target instead of showing a hardcoded paragraph. Pure frontend work.

Then decide: Tier 2 (wire real logs, show Phase 2 data when available) or Tier 3 (tissue heatmap, pathway enrichment) based on what matters most for demos/users.
