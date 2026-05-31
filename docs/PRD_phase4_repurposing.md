# PRD — Phase 4: Drug Repurposing Branch

**Maps to:** Human Pipeline.md §PHASE 4
**Celery queue:** `cpu` (Vina, DB pulls), `hosted` (DiffDock NIM, Boltz-2 Neurosnap), `llm`
**Depends on:** Phase 3 routing (`P4_repurpose` branch)

---

## Goal

For each target, find **existing approved/clinical drugs** that could be repurposed against it, validated by triangulating three independent signals: (1) docking, (2) LINCS reverse-signature, (3) prior clinical evidence. Output top-`candidates_per_target_max` repurposing candidates with evidence.

Runs when `intent_mode ∈ {explore, repurpose}`.

---

## Inputs Required From You

### Software (local)
- conda env `rxdis`: AutoDock Vina, ADFRsuite (`prepare_receptor4.py`), RDKit, `chembl_webresource_client`
- LM Studio server live

### Databases (local / API)
- ChEMBL (target mechanisms, phase-4 compounds)
- DrugBank XML (approved drugs) — requires registration download
- Open Targets `knownDrugs` (API, free)
- FDA approved-drug SMILES library (~3K) + ChEMBL phase-4 (~5K unique)

### Accounts / APIs
- CLUE.io (LINCS L1000) — `CLUE_API_KEY`
- NVIDIA NIM (DiffDock-V2) — `NIM_API_KEY`
- Neurosnap (Boltz-2 affinity) — `NEUROSNAP_API_KEY`

### From config
- `exclude_drugs` (pruned from library + results)
- patient cohort DE signature (optional; else public CREEDS/GEO via Enrichr)

---

## Process Steps (per target)

### 4.1 Approved-drug retrieval
- Parallel: ChEMBL `target_components`/`mechanisms`, DrugBank XML, OT `knownDrugs`.
- ≥1 approved drug confirms tractability.
- **Apply `exclude_drugs`** — remove before scoring.

### 4.2 LINCS reverse-signature query
- Disease signature: cohort DE (150 up / 150 down) or public signature.
- CLUE.io API against Touchstone subset → perturbagens with τ (negative = reversal).
- Keep τ < −90; cross-check DrugBank approval.
- Caveat baked in: LINCS is **one of three** signals (Lim & Pavlidis ~17% self-retrieval).

### 4.3 Virtual screening of approved-drug library
- A. AutoDock Vina local CPU (~10s/ligand; ~5K library ≈ 4h on 4 cores). Receptor prep via `prepare_receptor4.py`.
- B. Top 200 → DiffDock-V2 NIM rescoring (~$1 total).
- C. Top 50 → Boltz-2 affinity (Neurosnap).
- Keep Vina < −8.0 AND Boltz-2 log-µM < 1.0. No hits → relax to −7.0, re-examine pocket.

### 4.4 Triangulation
- `repurposing_score = 0.4·docking_norm + 0.35·LINCS_reversal + 0.25·prior_clinical`.
- Top `candidates_per_target_max` per target.

---

## Local-LLM Decision Points

| Gate | Decision | Output schema |
|---|---|---|
| `4.2_lincs_crosscheck` | for each τ<−90 hit: mechanistic plausibility, off-target relevance, feasibility (CNS penetration if needed) | `[{drug,plausible,concerns,feasibility}]` |
| `4.4_repurposing_narrative` | per candidate: 4-sentence repurposing case | `{title,verdict,evidence[],risk}` |

---

## I/O Contract

**Input:** Phase 3 routing + Phase 2 structure/pocket per target.

**Output (`phase_results.output_json` for phase 4):**
```json
{"repurposing":{
  "TGFB1":[
    {"drug":"niclosamide","vina":-9.5,"boltz2_log_uM":0.3,"lincs_tau":-88,
     "repurposing_score":0.72,"narrative":"...","prior_clinical":"antifibrotic lit"}
  ]
}}
```
Writes rows to `candidates` table with `kind='repurposing'`.

---

## Success Criteria

1. Reproduces known approved-drug pairs for ≥3 targets (e.g., baricitinib/COVID-19 via LINCS).
2. `exclude_drugs` never appear in output.
3. Each candidate has all three signal values populated (docking, LINCS, clinical).
4. Vina + Boltz-2 thresholds enforced; relaxation path triggers on zero hits.

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| Zero candidates >0.5 | mark "no obvious repurposing path"; rely on P5/P6 |
| LINCS no reversal signal | proceed with docking + clinical only (2 signals); note in narrative |
| NIM throttled | reroute DiffDock to Neurosnap/HuggingFace; defer |
| No approved drugs for target | skip 4.1 tractability boost; still run docking on FDA library |
