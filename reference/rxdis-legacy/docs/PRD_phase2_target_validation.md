# PRD — Phase 2: Target Validation (In Silico)

**Maps to:** Human Pipeline.md §PHASE 2
**Celery queue:** `cpu` (DB lookups, fpocket, AlphaMissense), `hosted` (NIM/Modal), `llm` (interpretation)
**Depends on:** Phase 1 `ranked_targets`

---

## Goal

For each of the top-N targets, decide whether it is a **real, druggable, safe** drug target. Produce a `validation_score` (0–1) with SHAP attributions and a structure + pocket + safety profile that downstream design phases consume. Drop weak targets before expensive design.

---

## Inputs Required From You

### Software (local)
- conda env `rxdis`: `fpocket` (compiled), `biopython`, `pdbfixer`, `openmm` (cryptic pockets), `xgboost`, `shap`, `IUPred3` (or equivalent), `DeepTMHMM` (or API)
- LM Studio server live

### Databases (local)
- DepMap `CRISPR_gene_effect.csv` (essentiality)
- AlphaMissense `AlphaMissense_hg38.tsv.gz` (variant pathogenicity)
- STRING (PPI confidence, reused from Phase 1)
- GTEx TPM + Human Protein Atlas (tissue safety)

### Accounts / APIs
- AlphaFold DB (free, per-UniProt fetch)
- NVIDIA NIM (ESMFold) — `NIM_API_KEY`
- AlphaFold Server (AF3 complexes) — session/key
- Modal (ProteomeLM-Ess/PPI Docker) — `MODAL_TOKEN`
- AlphaGenome DeepMind preview (free non-commercial)
- PockDrug-Server (browser automation — Playwright), CASTp (optional)
- RCSB PDB REST, UniProt REST, GTEx REST, HPA REST (free)

---

## Process Steps (per target)

### 2.1 Essentiality
- DepMap Chronos median + selective-lineage list (local).
- Non-oncology silent in DepMap → ProteomeLM-Ess via Modal (~$0.10/target).
- **`indication_type` applies:** core-essential + non-oncology → high-tox flag, −25% aggregate; oncology prefers selective essentiality.

### 2.2 Structure acquisition (routing order)
1. PDB (RCSB, ≥95% identity) → 2. AlphaFold DB (instant) → 3. ESMFold NIM (novel) → 4. AF Server AF3 (complexes) → 5. OmegaFold/Boltz-1 (ultra-dynamic).
- median pLDDT <70 → route to 2.6. Domain pLDDT >80 → use that domain only.

### 2.3 Pocket detection & druggability
- fpocket (CPU) → PockDrug-Server (browser, ~30s/pocket) → CASTp cross-check → cryptic (OpenMM 50ns implicit OR P2Rank/Neurosnap).
- max druggability <0.5 AND no cryptic → disable SM branch.
- membrane: restrict fpocket to extracellular domain (OPM boundary).

### 2.4 Variant / regulatory effect
- AlphaMissense lookup (local, instant); AlphaGenome (non-coding) preview API.
- Multiple AM >0.8 missense segregating with disease → +10% boost.

### 2.5 PPI validation & off-target
- STRING confidence; ProteomeLM-PPI via Modal; SwissTargetPrediction later when SMILES exists.
- **`selectivity_target` applies:** add as explicit anti-target in off-target hazard list.

### 2.6 Disordered / membrane / dark-genome subroutine
- Trigger: pLDDT <70 OR >40% disorder OR DeepTMHMM positive OR Tdark.
- Disordered → IUPred3, restrict to ordered domains, consider PROTAC.
- Membrane → extract ECD only. Tdark → literature + ARCHS4 co-expression; flag "speculative".

### 2.7 Tissue expression & safety
- GTEx REST + HPA REST. **`tissue_of_interest` is the default tissue** (avoids wrong-default GTEx tissue).
- Critical-tissue flag (heart/brain/kidney TPM >10) → require selectivity strategy.

### 2.8 Tractability assessment & modality hint
- Rule engine over OT tractability + 2.1–2.7 → SM/AB/PROTAC/peptide/oligo eligibility.
- **LLM gate** for edge cases (gain-of-function → degradation, borderline pocket, etc.).

### 2.9 Aggregate validation score + SHAP
- XGBoost over STRING centralities + Node2Vec vs DepMap labels (AUROC ~0.93 ref); GradientSHAP attributions.
- Select `validation_score > 0.5` → Phase 3. If <3 pass → lower to 0.3 + warn.
- Seeded targets pass regardless (flagged).

---

## Local-LLM Decision Points

| Gate | Decision | Output schema |
|---|---|---|
| `2.2_plddt_domains` | which residue ranges are confidently folded; is functional domain ordered; strategy | `{ordered_ranges[],disordered_ranges[],functional_domain_ordered,strategy}` |
| `2.3_pocket_selection` | most therapeutically relevant pocket given mutations/biology | `{selected_pocket,reason,strategy}` |
| `2.8_tractability_edge` | modality scores + primary recommendation for edge cases | `{SM,PROTAC,peptide,AB,oligo,primary_recommendation,key_reasoning}` |
| `2.9_shap_narrative` | SHAP values → plain-English evidence summary | `{summary}` |

---

## I/O Contract

**Input:** Phase 1 `ranked_targets`.

**Output (`phase_results.output_json` for phase 2):**
```json
{"validated_targets":[
  {"symbol":"TGFB1","validation_score":0.79,"seeded":false,
   "structure":{"source":"AFDB","uniprot":"P01137","median_plddt":88},
   "pockets":[{"id":"P1","druggability":0.71,"strategy":"interface"}],
   "essentiality":{"chronos":-0.2,"is_core_essential":false,"loeuf":0.42},
   "variants":{"high_path_missense":14},
   "safety":{"critical_tissue_flag":false,"tsi":0.61},
   "modality":{"SM":0.7,"AB":0.85,"peptide":0.75,"primary":"AB","secondary":"peptide"},
   "shap":{"druggability":0.18,"eigenvector":0.14,"gwas":0.12},
   "evidence_summary":"..."}
]}
```
Updates the `targets` table rows with `validation_score`, `modality_*`, `evidence_trail`. Stores structure PDB → Supabase Storage.

---

## Success Criteria

1. For KRAS G12C, identifies the cryptic switch-II pocket and flags covalent strategy.
2. Correct modality on ≥5/7 benchmark targets.
3. `tissue_of_interest` is used for expression queries (no wrong-default tissue).
4. `selectivity_target` appears in every target's off-target hazard list.
5. Structure routing falls through correctly (PDB→AFDB→ESMFold) and records the source used.

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| pLDDT <70 throughout | 2.6 disordered subroutine; restrict to ordered fragments; consider PROTAC |
| All pockets undruggable | disable SM; force peptide/biologic (P6) and/or PROTAC |
| AF Server quota hit | ESMFold NIM for non-complex; park AF3 to next day |
| Tdark, zero functional info | flag "very speculative"; still allow if seeded |
| <3 targets pass 0.5 | lower threshold to 0.3, warn |
