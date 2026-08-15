# PRD — Phase 3: Modality Selection Decision Logic

**Maps to:** Human Pipeline.md §PHASE 3
**Celery queue:** `cpu` + `llm` (grey-zone reasoning)
**Depends on:** Phase 2 `validated_targets`

---

## Goal

For each validated target, decide **which drug modality branch(es)** to pursue (small molecule, PROTAC, antibody, peptide, oligo) and assign branch routing for Phases 4/5/6. This is a fast, mostly-local rule engine with an LLM tie-breaker for borderline cases, gated by `intent_mode`.

---

## Inputs Required From You

### Software
- conda env `rxdis` (pure Python rule engine)
- LM Studio server live (grey-zone gate only)

### Databases / APIs
- ChEMBL (chemical-matter check — reused from Phase 2)
- No new downloads.

### From config
- `intent_mode` (gates which branches are even eligible)
- `modality_preference` (user bias)
- `seed_smiles` (forces SM optimization branch for that target)

---

## Process Steps

### 3.1 Rule-engine scoring (per target, local)
```
modality_score = {}
if pocket_druggability > 0.5 AND chembl_has_chemical_matter(target):
    modality_score["SM"] = 0.8*druggability + 0.2*chembl_evidence
if (intracellular AND has_weak_binder) OR (intracellular AND E3_proximity):
    modality_score["PROTAC"] = 0.7
if extracellular OR transmembrane_with_ECD:
    modality_score["AB"] = 0.85
if PPI_inhibitor_use_case OR small_extracellular:
    modality_score["peptide"] = 0.75
if intracellular_undruggable AND mRNA_detectable:
    modality_score["oligo"] = 0.6
primary   = argmax(modality_score)
secondary = next-highest > 0.5
```

### 3.2 Apply intent_mode routing
- `repurpose` → mark target for Phase 4 only (no de novo branch).
- `de_novo` → skip Phase 4; route to P5 (SM/PROTAC) or P6 (AB/peptide) by `primary`.
- `explore` → Phase 4 (always) + primary de novo branch (+ secondary if budget allows).

### 3.3 Apply config overrides
- `modality_preference != any` → bias/clamp toward chosen modality.
- `seed_smiles` present for target → force SM branch, set Phase 5 to optimization-only.

### 3.4 Repurposing priority flag
*(Updated to consume `clinical_stage` from Phase 1 step 1.2b rather than a binary approved-or-not check. The old binary conflated "approved drugs exist for any disease" with "approved drugs exist for this specific indication.")*

```
if clinical_stage == "approved":                         repurposing_priority = "HIGH"
elif clinical_stage in {"clinical_ph2", "clinical_ph3"}: repurposing_priority = "MEDIUM"
elif clinical_stage == "clinical_ph1":                   repurposing_priority = "LOW_CLINICAL"
else:                                                    repurposing_priority = "LOW"
```

Supplementary LINCS/CLUE signature match (unchanged) can upgrade `LOW` → `MEDIUM` independently.

Budget routing by priority:
- `HIGH` → skip LINCS sweep; proceed directly to Phase 4 docking with known approved structures.
- `MEDIUM` → run LINCS sweep + dock approved structures; flag as "competitive indication."
- `LOW_CLINICAL` → run LINCS sweep; note Phase 1 trial failures and reasons (inform design choices in Phase 5/6).
- `LOW` → full LINCS/CLUE sweep; consider this a de novo target for repurposing purposes.

**`novelty_mode` interaction:** if `novelty_mode=True` was set in the run, targets with `repurposing_priority == "HIGH"` that were auto-excluded from Phase 1 scoring are still eligible for Phase 4. `novelty_mode` excludes well-known targets from the *scoring competition* to surface novel targets, but repurposing existing approved drugs onto any validated target (including known ones) is still scientifically valid and cost-effective.

---

## Local-LLM Decision Points

| Gate | When | Decision | Output schema |
|---|---|---|---|
| `3_modality_greyzone` | scores within 0.1 of each other, or gain-of-function mutation, or borderline druggability (0.45–0.55) | choose modality with reasoning + concerns | `{decision, confidence, concerns[]}` |

Example resolved nuance: gain-of-function mutant with weak pocket → PROTAC degradation over inhibition.

---

## I/O Contract

**Input:** Phase 2 `validated_targets`.

**Output (`phase_results.output_json` for phase 3):**
```json
{"routing":[
  {"symbol":"TGFB1","primary":"AB","secondary":"peptide",
   "branches":["P4_repurpose","P6_biologic"],
   "repurposing_priority":"HIGH","modality_scores":{"SM":0.7,"AB":0.85,"peptide":0.75}},
  {"symbol":"LRRK2","primary":"SM","secondary":"PROTAC",
   "branches":["P4_repurpose","P5_small_molecule"],
   "repurposing_priority":"HIGH","seed_smiles_opt":false}
]}
```

---

## Success Criteria

1. Every target gets ≥1 branch; `explore` targets always include Phase 4.
2. `intent_mode=repurpose` produces zero de-novo branches.
3. `seed_smiles` target routes to SM optimization-only.
4. Borderline cases get an LLM decision logged in `decisions`.
5. KRAS-like (intracellular, druggable pocket) → SM/PROTAC; PD-L1-like (extracellular) → AB.

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| No modality scores >0.5 | route to repurposing only; flag "hard target" |
| Conflicting signals | LLM grey-zone gate resolves; if still unclear, run both primary+secondary |
