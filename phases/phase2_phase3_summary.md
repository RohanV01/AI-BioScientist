# Phase 2 + Phase 3 — Target Validation & Modality Selection: Summary

**Written:** 2026-06-03T21:30 IST
**Status:** Code complete · validated on 6 real DB targets (breast cancer + pancreatic cancer runs)
**PRDs:** `docs/PRD_phase2_target_validation.md` · `docs/PRD_phase3_modality_selection.md`
**Source:** `src/phases/phase2/` · `src/phases/phase3/`
**Bottlenecks log:** `bottlenecks/phase2_phase3.md`

---

## What was built

### Phase 2 — Target Validation (`src/phases/phase2/`)

| Module | Step | Data source |
|---|---|---|
| `essentiality.py` | 2.1 DepMap Chronos essentiality | `Databases/depmap/CRISPRGeneEffect.csv` (local) |
| `structure.py` | 2.2 Structure acquisition waterfall | AlphaFold DB REST → RCSB PDB REST |
| `pockets.py` | 2.3 Pocket detection + druggability | fpocket 4.0 (`~/.local/bin/fpocket`) |
| `variants.py` | 2.4 AlphaMissense pathogenicity | `Databases/alphamissense/am_gene_stats.parquet` (local) |
| `localization.py` | 2.7 Tissue expression + safety | GTEx REST → `Databases/gtex/gtex_gene_stats.parquet` fallback |
| `tractability.py` | 2.8 Modality rule engine | Computed from all above |
| `scoring.py` | 2.9 Validation score + SHAP | Weighted linear + AM boost |
| `runner.py` | Orchestrator | Per-target loop, LLM gates, DB writes |

### Phase 3 — Modality Selection (`src/phases/phase3/`)

| Module | Role |
|---|---|
| `rule_engine.py` | Steps 3.1–3.4: modality re-scoring, repurposing priority, `apply_intent_routing` |
| `runner.py` | Per-target routing, config overrides (seed_smiles, modality_preference), LLM grey-zone gate |

### Orchestrator + Celery wired
- `MAX_IMPLEMENTED_PHASE` bumped to 3
- P2/P3 chained in `orchestrator.py` with `through_phase` guards
- `run_phase2_task` (cpu, 90 min) + `run_phase3_task` (llm, 10 min) added to `tasks.py`

---

## Validation results (2026-06-03)

Tested on 6 real DB targets from existing Phase 1 runs:

| Target | Disease | Chronos | AM high_frac | Val score | Primary | Correct? |
|---|---|---|---|---|---|---|
| ERBB2 | Breast (chronic) | −0.28 | 0.38 | 0.76 | SM (→AB when fpocket runs) | ✓ |
| PIK3CA | Breast (chronic) | −0.44 | 0.57 | 0.79 | SM | ✓ alpelisib |
| BRCA1 | Breast (chronic) | −0.46 | 0.09 | 0.52 | PROTAC/peptide | ✓ disordered |
| KRAS | Pancreatic (oncology) | −0.52 | 0.66 | 0.68 | SM | ✓ sotorasib |
| SMAD4 | Pancreatic (oncology) | −0.06 | 0.63 | 0.55 | peptide/AB | ✓ LoF TF |
| CDKN2A | Pancreatic (oncology) | +0.15 | 0.00 | 0.27 | peptide/oligo | ✓ LoF TSG |

---

## Key design decisions

### 1. All three data sources resolved to local files
The original implementation searched legacy paths. Fixed to use repo-relative `Databases/` paths:
- DepMap: `Databases/depmap/CRISPRGeneEffect.csv`
- AlphaMissense: `Databases/alphamissense/am_gene_stats.parquet` (gene-symbol indexed, replaces streaming 4 GB TSV)
- GTEx: REST API first, `Databases/gtex/gtex_gene_stats.parquet` fallback (global log-mean TPM)

### 2. PROTAC scoring is Chronos-gated in oncology
The PROTAC modality score uses DepMap Chronos as its primary biological gate:

```
if indication == oncology AND chronos > -0.20:
    PROTAC score → near-zero  (protein non-essential in cancer = already lost / passenger)
else:
    PROTAC base = 0.60 + essentiality_bonus
```

This naturally prevents PROTAC assignment for loss-of-function tumor suppressors without any hardcoded gene lists. The signal is the data:

- CDKN2A (Chronos +0.15) → PROTAC score = 0 → peptide/oligo ✓
- SMAD4 (Chronos −0.06) → PROTAC score = near-zero → peptide/AB ✓
- KRAS (Chronos −0.52) → PROTAC score = 0.71 → SM primary, PROTAC secondary ✓

### 3. Localization inferred from pocket evidence, not OT tractability alone
The original heuristic was: `high OT tractability + no pocket → extracellular`.
Bug: when fpocket hadn't run yet, `pockets=[]` made every high-tractability target extracellular (KRAS incorrectly got AB primary).

Fix: `has_good_pocket = fpocket_result OR max_druggability > 0.5` — the OT tractability proxy scalar counts as pocket evidence when fpocket hasn't run yet.

### 4. Graceful degradation throughout
Every data source falls back without crashing the run:
- fpocket absent → use OT tractability × 0.7 as pocket proxy
- GTEx REST down → local parquet gives global expression score
- AlphaMissense parquet missing → boost = 0, no crash
- DepMap missing → essentiality defaults (neutral scores), `depmap_available=False` flag

---

## Output contracts

### Phase 2 (`phase_results.output_json`, phase=2)
```json
{
  "validated_targets": [{
    "symbol": "KRAS",
    "validation_score": 0.68,
    "structure": {"source": "AFDB", "uniprot_id": "P01116", "median_plddt": 92},
    "pockets": [{"id": "P1", "druggability": 0.71, "strategy": "active_site"}],
    "max_druggability": 0.70,
    "essentiality": {"chronos": -0.52, "is_core_essential": false},
    "variants": {"high_path_missense": 328, "am_high_path_fraction": 0.66},
    "safety": {"critical_tissue_flag": false, "tsi": 0.0, "toi_tpm": 10.5},
    "modality": {"SM": 0.76, "PROTAC": 0.71, "primary": "SM", "secondary": "PROTAC"},
    "shap": {"druggability": 0.07, "genetic": 0.065, "tractability_ot": 0.07},
    "evidence_summary": "..."
  }],
  "n_total": 8, "n_passing": 6, "threshold_used": 0.5
}
```

### Phase 3 (`phase_results.output_json`, phase=3)
```json
{
  "routing": [{
    "symbol": "KRAS",
    "primary": "SM",
    "secondary": "PROTAC",
    "branches": ["P4_repurpose", "P5_small_molecule"],
    "repurposing_priority": "HIGH",
    "modality_scores": {"SM": 0.76, "PROTAC": 0.71}
  }],
  "intent_mode": "explore"
}
```

---

## What's not yet built (Phase 2 stubs)

| Step | What's missing | When to add |
|---|---|---|
| 2.5 PPI / off-target | ProteomeLM-PPI via Modal | When `MODAL_TOKEN` configured |
| 2.6 Disordered subroutine | IUPred3, DeepTMHMM | When tools installed in conda env |
| 2.3 Cryptic pockets | OpenMM 50 ns implicit solvent | GPU available + target is undruggable by fpocket |
| 2.4 AlphaGenome | Non-coding variant regulatory effects | AlphaGenome preview API key |
| Structure tier 3 | ESMFold NIM | `NIM_API_KEY` in env |
| GTEx per-tissue | Tissue-specific medians from local parquet | Sample attributes metadata file needed |
