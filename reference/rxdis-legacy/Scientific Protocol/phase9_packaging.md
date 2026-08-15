# Scientific Protocol — Phase 9: Output Packaging & Reproducibility

**Document version:** 1.0  
**Written:** 2026-06-03  
**Status:** Active — all packaging steps implemented  
**Corresponding implementation:** `src/phases/phase9/` — `assembler.py`, `runner.py`  
**See also:** `phases/phase9_summary.md`, `bottlenecks/phase9.md`

---

## 1. Why Reproducibility Packaging Matters in Computational Drug Discovery

### 1.1 The Reproducibility Crisis in Computational Science

Computational drug discovery has a well-documented reproducibility problem. Stodden et al. (2016, Science) surveyed 204 computational papers and found that only 26% provided sufficient information to reproduce the reported results, even in principle. In cheminformatics specifically, a 2021 survey by Walters & Barzilay (Journal of Medicinal Chemistry) found that approximately 40% of published virtual screening results could not be reproduced due to missing software versions, ambiguous scoring function parameters, or undisclosed preprocessing steps.

This has direct consequences for drug discovery programs: a computational screen that cannot be reproduced or interrogated cannot be used to:
- Validate a hit against new experimental data
- Extend the analysis to a new disease indication
- Audit for systematic errors that affect candidate prioritization
- Transfer the analysis to a collaborator or contract research organization (CRO)

The Phase 9 packaging protocol is designed to address all four requirements.

### 1.2 FAIR Principles Applied to Drug Discovery Pipelines

The FAIR data principles (Findable, Accessible, Interoperable, Reusable; Wilkinson et al. 2016, Scientific Data) were originally formulated for research datasets but apply equally to computational drug discovery outputs. Phase 9 implements each principle:

| Principle | Phase 9 Implementation |
|---|---|
| **Findable** | Supabase Storage URL in `runs` table; package indexed by `run_id` |
| **Accessible** | Public URL from Supabase Storage; local zip as fallback |
| **Interoperable** | All outputs are JSON (structured) or standard formats (BibTeX, SMILES); no proprietary binary formats |
| **Reusable** | `run_metadata.json` with exact software versions and config; `README.md` with re-run command |

---

## 2. Version Pinning Strategy

### 2.1 Why Version Pinning is Critical

A cheminformatics pipeline's output is not fully reproducible without pinning the versions of every computational dependency. Consider:

- **RDKit:** Fingerprint generation algorithms changed between RDKit 2022.09 and 2023.03 (GetMorganFingerprintAsBitVect deprecated; GetMorganGenerator API introduced). A Morgan fingerprint computed with the old API is not bit-identical to one computed with the new API, producing different Tanimoto similarities and GP surrogate features.

- **XGBoost:** The PU learning model (Phase 1 `pu_model.py`) uses XGBoost. Model predictions can vary by ±0.01 between minor XGBoost versions due to floating-point handling changes. For border-case targets, this can change the rank order.

- **AutoDock Vina:** Vina 1.2.7 introduces improved atom-type handling relative to Vina 1.1.2. Vina scores are not portable across major versions.

- **ChEMBL database version:** ChEMBL 37 (the current version used) contains different compound-target associations than ChEMBL 35 or 36. A repurposing candidate identified in ChEMBL 37 may not be present in earlier versions.

### 2.2 `importlib.metadata` vs Conda Environment Export

Two common approaches to version pinning in Python environments:

**Option A — `conda env export > environment.yml`:**
- Captures all transitive dependencies and their exact versions
- Captures system-level libraries (CUDA, libGL, etc.)
- Can be used to recreate an identical conda environment
- **Limitation:** Creates a large file (100+ packages) that may be platform-specific (Linux vs macOS). The conda-lock file format is needed for full cross-platform reproducibility (Carpenter et al. 2021).

**Option B — `importlib.metadata.version(pkg)` for key packages (RxDis approach):**
- Records only scientifically relevant packages (rdkit, xgboost, sklearn, vina, etc.)
- Small and human-readable
- Does not include transitive dependencies or system libraries
- **Limitation:** Insufficient alone for exact environment reproduction; must be paired with a `requirements.txt` or `pyproject.toml` lock file

The RxDis Phase 9 uses Option B because:
1. The full `environment.yml` would be ~150+ lines and is better managed as part of the repository (`pyproject.toml` + `uv.lock`)
2. The 9 recorded packages cover all scientifically significant computations
3. The `run_metadata.json` is intended for scientific audit, not environment recreation — the repository's lock file handles the latter

**Recommendation:** For a production deployment, Phase 0 should additionally call `pip freeze > freeze.txt` or `uv export > requirements_freeze.txt` and store the output in Supabase as a run artifact. This provides the full environment snapshot without bloating the per-run package.

### 2.3 Non-Python Dependencies

| Dependency | Pinning method |
|---|---|
| AutoDock Vina binary | `vina --version` → reported in compute_log at Phase 4 |
| ChEMBL SQLite database | Filename `chembl_37.db` → version 37 extracted by regex |
| PrimeKG kg.csv | Hard-coded "2023.10" (the release used) |
| LM Studio model | `settings.LMSTUDIO_MODEL` env var (model name is version-sufficient for GGUF models) |
| GTEx v11 | Recorded in DB check output from Phase 0 |
| GWAS Catalog | Recorded by Phase 0 database check |

---

## 3. Package Contents: What Each File Contains and Why

### 3.1 `run_metadata.json`

**Purpose:** Exact config replay and provenance identification.

**Contains:**
- `run_id`: UUID that links this package to all Supabase records
- `disease`: Human-readable disease name (as provided by the user)
- `efo_id`: Standardized EFO/MONDO ontology identifier — enables consistent querying of Open Targets across re-runs
- `intent_mode`: `full`, `repurpose_only`, or `denovo_only` — determines which phases ran
- `db_versions`: Software and database versions (see Section 2)
- `config`: Key configuration parameters (target count cap, modality preference, seed targets, LLM provider)

**Why it matters:** A medicinal chemist re-running the pipeline 6 months later can inspect `run_metadata.json` to determine whether the ChEMBL version used for repurposing has been superseded (ChEMBL is updated quarterly) or whether a newer RDKit version changes the ADMET predictions.

### 3.2 `ranked_targets.json`

**Purpose:** Complete Phase 1 output with evidence trails for all ranked targets.

**Contains:** The full `targets` table rows for this run, ordered by Phase 1 rank. Each entry includes the complete `evidence_trail` dict (OT score, literature score, genetic score, PPI centrality, pathway score, tractability) and the final `aggregate_score`.

**Why it matters:** Enables retrospective auditing of why a target was ranked highly or poorly. If a new GWAS study finds a novel locus for the disease, the analyst can compare against `ranked_targets.json` to determine whether that gene was in the analysis (just ranked low) or was completely absent (missed by the OT + GWAS pull).

### 3.3 `targets/{SYMBOL}/target_validation.json`

**Purpose:** Phase 2 validation summary for each target.

**Contains:** Phase 2 structure quality, pocket descriptors summary, essentiality (DepMap Chronos), expression (GTEx tissue TPMs), localization (HPA subcellular), tractability bucket, modality primary/secondary from Phase 3.

**Why it matters:** A medicinal chemist reviewing candidates for KRAS needs to know: Is the AlphaFold structure reliable (pLDDT)? What is the best fpocket site? Is KRAS essential in cancer cell lines (yes, Chronos < -2.0)? Is there a structural basis for selectivity over NRAS/HRAS? All of this is in `target_validation.json`.

### 3.4 `targets/{SYMBOL}/pockets.json`

**Purpose:** fpocket binding site predictions with druggability scores.

**Contains:** All pockets detected by fpocket, ranked by druggability score. Each pocket includes centroid coordinates (cx, cy, cz), volume, docking box dimensions, and fpocket druggability score.

**Why it matters:** The pocket coordinates are the exact coordinates used to center Vina docking boxes in Phases 4, 5, and 8. If a candidate shows unexpected docking results, the analyst can inspect `pockets.json` to verify the correct pocket was used.

### 3.5 `targets/{SYMBOL}/candidates_*.json`

Three files per target, one for each candidate type:
- `candidates_repurposing.json` — Phase 4 repurposing hits
- `candidates_de_novo_sm.json` — Phase 5 de-novo small molecule candidates  
- `candidates_biologic.json` — Phase 6 biologic/peptide candidates

**Contains:** Complete candidate records including all Vina scores, ADMET/developability subscores, SMILES or sequence, Phase 8 combined score, passed/failed status, and the medicinal chemist brief.

**Why it matters:** The candidate files are the primary deliverable of the pipeline. A CRO synthesis team reads these files to identify which compounds to synthesize first.

### 3.6 `targets/{SYMBOL}/admet/{cid}_admet.json`

**Purpose:** Detailed ADMET profile for each small molecule candidate.

**Contains:** Per-property ADMET predictions from Phase 5 `score_admet()`: LogP, MW, TPSA, HBD/HBA counts, QED, hERG flag (none/medium/high), P-gp substrate flag, CYP3A4/2D6 inhibition flag, solubility (mg/mL), BBB penetration probability, plasma half-life estimate, disqualifying flags list.

**Why it matters:** The ADMET subscores in the candidates file are single-number summaries. The per-candidate ADMET JSON shows which specific properties drove the score. A medicinal chemist addressing a poor ADMET score needs to know: is the problem hERG (fix: reduce basic nitrogen pKa), solubility (fix: add hydrophilic substituents), or CYP inhibition (fix: remove planar aromatic systems)?

### 3.7 `compute_log.json`

**Purpose:** Cost transparency and performance profiling.

**Contains:** All `compute_log` table rows for this run, including: phase, step name, service (local/anthropic/openai/nim), wall time in seconds, and cost in USD.

**Why it matters:** Enables cost attribution across phases. A run that costs $0.50 can be broken down: Phase 1 literature extraction ($0.003), Phase 4 NIM docking ($0.35), Phase 6 BoltzGen ($0.14), etc. This informs budget allocation decisions for future runs.

### 3.8 `decisions.json`

**Purpose:** LLM gate audit trail — what the AI decided and with what model.

**Contains:** Compact format (prompts redacted): phase, gate ID, LLM provider, LLM model name, parsed decision JSON.

**Why it matters:** Every LLM-influenced decision in the pipeline (EFO disambiguation, weight tuning, hub interpretation, modality routing, MPO iteration review, self-audit) is recorded with its structured output. If the final candidate list seems biased toward a particular scaffold or modality, the analyst can trace back to the `1.8_weight_tuning` decision to see what scoring weights were applied.

**Full audit:** The Supabase `decisions` table contains full prompts and raw LLM responses. Query with:
```sql
SELECT gate, llm_model, decision_json, raw_response
FROM decisions
WHERE run_id = '{run_id}'
ORDER BY phase, created_at;
```

### 3.9 `citations.bib`

**Purpose:** Scientific provenance — the methods cited by the pipeline.

**Contains:** BibTeX entries for the key algorithmic and database papers underlying RxDis computations.

**Why it matters:** Any publication arising from a RxDis analysis must cite the computational methods used. The `citations.bib` provides all required method citations in a format compatible with LaTeX/Overleaf workflows. Import directly with `\bibliography{citations}`.

### 3.10 `README.md`

**Purpose:** Executive summary for a medicinal chemist reading the package without running the pipeline.

**Structure:**
- **Overview:** Disease, EFO ID, intent mode, indication type
- **Top Targets:** Bullet list of Phase 1 top-5 symbols with rationale
- **Key Findings:** Number of validated candidates, top candidates by combined score
- **Caveats & Limitations:** Self-audit concerns, MD deferral, model limitations
- **Reproducibility:** Exact `kickoff.py` command, DB version notes, where to find full audit trail

The README is generated by the `9_executive_summary` LLM gate and reflects the specific disease and candidates found in the run — it is not a generic template.

---

## 4. Attrition Funnel Self-Audit: Scientific Rationale

### 4.1 What Is the Expected Attrition in Drug Discovery?

Drug discovery programs have predictable attrition at each stage. For a well-functioning computational pipeline:

| Transition | Expected attrition | Normal range |
|---|---|---|
| Disease targets (literature) → P1 ranked | N/A (all assembled) | 10–100 ranked targets |
| P1 ranked → P2 validated | 20–40% dropped | >75% drop indicates structure prediction failures |
| P2 validated → P4 candidates | ~0% (all targets screened) | Any target with a pocket gets candidates |
| P4 repurposing candidates → P4 passed | 30–70% dropped | Threshold ≥ 0.30; very stringent for targets with no known drugs |
| P7 Pareto front → P8 validated | 20–50% dropped | Combined score ≥ 0.45; higher drop rate indicates weak P5/P6 generation |
| P8 passed → packaged | 0% (all passed are included) | Complete set |

### 4.2 Anomaly Detection Thresholds

| Anomaly | Hard-coded check | LLM check |
|---|---|---|
| Phase 1 returns 0 targets | `audit_passed = False` | Redundant |
| Phase 8 passes 0 candidates with >0 validated targets | Recommended rerun flag | LLM confirms |
| Phase 2 drops >75% of Phase 1 targets | Phase 2 quality warning | LLM interprets |
| Phase 4 completes in < 30 s with > 0 candidates | Docking skip warning | LLM may catch |

### 4.3 When Is Rerun Recommended?

`recommended_rerun = True` should be set when:
1. `n_targets_p1 == 0` (total pipeline failure — Phase 1 EFO mapping or OT API issue)
2. `n_candidates_passed_p8 == 0 AND n_targets_p2 > 0` (Phase 8 scoring too strict, or Phase 5/6 generated no viable candidates)
3. LLM self-audit identifies a specific data quality issue (e.g., "AlphaFold structure pLDDT uniformly < 70 for all targets — pocket detection unreliable")

A `recommended_rerun = True` flag does not automatically trigger a rerun — it is a signal to the analyst to inspect the run before treating any outputs as valid.

---

## 5. Supabase Storage Architecture

### 5.1 Bucket and Path Structure

```
Storage bucket: artifacts (public read, service-key write)
Path: runs/{run_id}/package.zip
```

The `runs/{run_id}/` prefix ensures that multiple artifacts per run can coexist without collision (future: individual SDF files, trajectory files, crystal structures). The `run_id` is a UUID4 generated at run creation time, providing guaranteed uniqueness.

### 5.2 Public URL Access

The public URL returned by `get_public_url(storage_path)` follows the pattern:
```
https://{SUPABASE_PROJECT_REF}.supabase.co/storage/v1/object/public/artifacts/runs/{run_id}/package.zip
```

This URL is:
- Stored in `runs.package_url` in the Supabase database
- Returned in the Phase 9 output JSON
- Displayed as a download button in the React frontend (`EngineRoom.tsx`, `Scorecard.tsx`)

### 5.3 Upload Semantics

The `upload_package()` function uses a remove-then-upload pattern to handle overwrites (e.g., if Phase 9 is re-run for the same `run_id`):

```python
try:
    storage.upload(path, data, options)
except Exception:
    storage.remove([path])    # remove existing
    storage.upload(path, data, options)   # re-upload
```

This is necessary because the Supabase Storage API returns an error on duplicate paths rather than overwriting. The pattern has a known limitation: if the upload in the second `try` also fails (e.g., storage quota exceeded), the failure is silent. See `bottlenecks/phase9.md` H1 for the fix.

---

## 6. Re-Running a Published Analysis

To reproduce a published RxDis analysis exactly, a collaborator needs:

1. **The `run_metadata.json`** from the package — provides disease name, intent mode, and config
2. **The exact software versions** from `db_versions` in `run_metadata.json`
3. **The same local databases** (ChEMBL 37, PrimeKG 2023.10, STRING v12.0, DepMap, AlphaMissense)
4. **The same LLM model** for all LLM-gated decisions (or accepts that different model decisions may change some rankings)

Re-run command (from `README.md`):
```bash
python scripts/kickoff.py \
    --disease "pancreatic cancer" \
    --intent full \
    --target_count_max 20 \
    --seed_targets KRAS \
    --llm_provider lmstudio \
    --llm_model "qwen3-8b-mlx"
```

**Note on LLM non-determinism:** LLM gate decisions (weight tuning, hub interpretation, modality routing) introduce non-determinism even with the same model and `temperature=0.1`. Different runs may produce slightly different target rankings and candidate selections. This is an irreducible source of variability in pipelines that include LLM decision gates. The `decisions.json` in the package records what decisions were made in the original run, enabling the analyst to compare the re-run's decisions against the original to assess divergence.

For fully deterministic reproduction, the `decisions` table can be used to replay LLM decisions from cache rather than re-querying the LLM. This feature is not yet implemented in RxDis as of 2026-06-03.
