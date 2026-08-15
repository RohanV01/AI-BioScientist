# PRD — Phase 5: De Novo Small Molecule Design

**Maps to:** Human Pipeline.md §PHASE 5
**Celery queue:** `cpu` (RDKit filters), `gpu` (REINVENT4 local), `hosted` (NIM GenMol/DiffDock, Neurosnap Boltz-2, RunPod library docking, ADMETlab), `llm`
**Depends on:** Phase 3 routing (`P5_small_molecule` branch)

---

## Goal

For SM/PROTAC-routed targets, **design novel drug-like molecules** that bind the validated pocket, pass medicinal-chemistry filters and ADMET, and rank well by affinity. Output top-20 candidates per target. If `seed_smiles` is set, skip generation and run optimization-only on the seed.

Runs when `intent_mode ∈ {explore, de_novo}`.

---

## Inputs Required From You

### Software (local)
- conda env `rxdis`: RDKit (FilterCatalog, QED, SA), REINVENT4 (~8 GiB GPU — tight on 6 GB, batches 100–500), AutoDock Vina / QuickVina-W, ADMET-AI (local Chemprop)
- LM Studio server live

### Databases (local / API)
- **Enamine REAL Diverse Drug-Like slice (~5 GB)** — required here (deferred from Phase 0 if mode was repurpose)
- ChEMBL approved drugs (Tanimoto novelty reference)
- ZINC22 tranches (optional)

### Accounts / APIs
- NVIDIA NIM (GenMol, DiffDock-V2) — `NIM_API_KEY`
- Neurosnap (Boltz-2) — `NEUROSNAP_API_KEY`
- RunPod (A100 burst for 5M library docking, ~$3) — `RUNPOD_API_KEY`
- ADMETlab 3.0 API (free), SwissADME (browser), AlphaFold Server (AF3 complex, optional)

### From config
- `seed_smiles` (skip generation, optimize these)
- `selectivity_target` (off-target penalty in ADMET)
- `indication_type` (ADMET threshold severity)

---

## Process Steps (per target)

### 5.1 Pocket-targeted library screen
- Enamine REAL Diverse (~5M). Vina locally on 100K subset OR QuickVina-W on RunPod A100 for full 5M (~$3).
- Keep Vina < −8.0 AND RMSD across 3 runs < 2 Å. Top 1,000 hits.

### 5.2 De novo generation conditioned on pocket
- **If `seed_smiles` set → SKIP, go to 5.3 with seeds.**
- Else preference order: REINVENT4 (LibInvent/LinkInvent + scoring QED+SA+docking+Boltz-2) → GenMol NIM → PocketGen/TamGen (Neurosnap) → DiffSBDD (Replicate).
- 5K–10K SMILES; keep top 1,000 by Pareto (docking, QED, SA).

### 5.3 Filtering (local RDKit)
- PAINS, Lipinski Ro5, Veber, Egan, REOS, SA score (or RAscore).
- Novelty: Tanimoto < 0.4 vs ChEMBL approved (unless intentional analog).
- → ~200–500 molecules.

### 5.4 ADMET prediction
- ADMETlab 3.0 API (119 endpoints) + SwissADME cross-check + ADMET-AI local.
- Drop if >2 critical endpoints fail (hERG, AMES, hepatotox, BBB if non-CNS).
- **`indication_type` adjusts severity; `selectivity_target` off-target hit = penalty.**

### 5.5 Re-dock & rescore
- DiffDock-V2 NIM (top pose) + Boltz-2 Neurosnap (affinity) + AF3 Server (complex w/ cofactors, optional).
- Top 20 by Boltz-2.

### 5.6 Lead optimization
- MMP analysis (RDKit) + REINVENT4 LibInvent / Mol2Mol R-group; loop 5.4–5.5.
- Halt when no analog improves >2× affinity AND ADMET; lock parent.

---

## Local-LLM Decision Points

| Gate | Decision | Output schema |
|---|---|---|
| `5.3_pains_override` | flagged molecule with exceptional docking — drop / keep-flagged / keep-as-analog-seed | `{decision,reasoning}` |
| `5.4_admet_context` | interpret ADMET given indication + population; verdict | `{overall_verdict,disqualifying[],concerns[],positives[]}` |
| `5.6_opt_direction` | from MMP results, top 3 structural modifications to pursue | `{modifications:[{change,expected_benefit,risk,priority}]}` |

---

## I/O Contract

**Input:** Phase 3 routing + Phase 2 pocket/structure.

**Output (`phase_results.output_json` for phase 5):**
```json
{"de_novo_sm":{
  "LRRK2":[
    {"id":"DNSM_001","smiles":"...","vina":-10.1,"boltz2_log_uM":0.2,
     "qed":0.74,"sa":2.9,"tanimoto_to_approved":0.31,
     "admet":{"hERG":"low","AMES":"neg","BBB":"pos"},"combined_pre8":0.81}
  ]
}}
```
Writes `candidates` rows with `kind='de_novo_sm'`, SMILES, subscores; poses → Storage.

---

## Success Criteria

1. ≥1 generated molecule Tanimoto >0.6 to a known approved drug (validation of the generator on a well-studied target).
2. `seed_smiles` set → generation skipped, optimization runs on seeds.
3. All output passes PAINS + Ro5 + ADMET gates (or carries explicit override flag).
4. `selectivity_target` off-target hits penalized in ranking.
5. Top 20 ranked by Boltz-2 with full subscores.

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| Undruggable pocket | redirect to Phase 6 (peptide) or PROTAC |
| All molecules fail ADMET | restart 5.2 with ChEMBL scaffold seed |
| No MD-stable pose (found in P8) | drop; next target |
| REINVENT4 OOM on 6 GB | reduce batch to 100; or route generation to GenMol NIM |
| RunPod unavailable | screen 100K subset locally instead of 5M |
