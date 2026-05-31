# Phase 2 + Phase 3 — Implementation Summary (M2)

**Status:** Code-complete. Imports + pure-logic units validated (no LLM/network).
Not yet run end-to-end against the live local model (GPU-contention rule — don't
launch an LLM-backed run while another is in flight).

Maps to: `docs/PRD_phase2_target_validation.md`, `docs/PRD_phase3_modality_selection.md`,
MASTER_PRD §12 milestone **M2** (KRAS G12C → cryptic switch-II pocket, covalent SM).

---

## What was built

### Phase 2 — Target Validation (`src/phases/phase2/`)
Per-target, over Phase 1's top-N `ranked_targets`:

| File | Step | What it does |
|---|---|---|
| `uniprot.py` | — | symbol → reviewed human UniProt (REST), cached; drives structure/variants/chembl |
| `essentiality.py` | 2.1 | DepMap Chronos median, pan-essential + selective-fraction flags; batched single read |
| `structure.py` | 2.2 | routing fallthrough PDB (PDBe SIFTS) → AlphaFold DB → ESMFold NIM; pLDDT parsed by hand from B-factors; confident/disordered residue ranges |
| `pockets.py` | 2.3 | fpocket when present (parses Drug Score); else OT-tractability proxy. `max_drug < 0.5` → SM branch disabled |
| `variants.py` | 2.4 | AlphaMissense high-pathogenicity missense count via `grep` (batched single pass over the 5.4 GB file) |
| `localization.py` | 2.6 | HPA-driven intracellular / membrane(+ECD) / secreted classification; UniProt-keyword fallback |
| `expression.py` | 2.7 | HPA RNA tissue specificity → TSI, critical-tissue flag (heart/brain/kidney), `tissue_of_interest` check |
| `chembl.py` | 2.8 | chemical-matter check (local SQLite): distinct bioactive/potent compounds + max clinical phase |
| `tractability.py` | 2.8 | rule engine → per-modality scores {SM,PROTAC,peptide,AB,oligo}; LLM edge gate `2.8_tractability_edge`; `selectivity_target` added to off-target hazards |
| `scoring.py` | 2.9 | 7-feature validation_score + per-feature attributions; LLM narrative `2.9_shap_narrative` |
| `runner.py` | — | orchestrates, applies pass threshold (>0.5; →0.3 if <3 pass; seeded always pass), writes `targets` rows |

### Phase 3 — Modality Selection (`src/phases/phase3/`)
| File | What it does |
|---|---|
| `rule_engine.py` | consumes Phase 2 modality scores; `modality_preference` bias (3.3); grey-zone LLM gate `3_modality_greyzone`; `repurposing_priority` from ChEMBL max_phase (3.4); `intent_mode` → branches (3.2); `seed_smiles` → forced SM optimization-only |
| `runner.py` | routes passing targets, writes `modality_primary/secondary`, emits `routing` contract + branch summary |

### Wiring
- `src/workers/tasks.py` — added `run_phase2_task` (queue `hosted`, 3h limit) and `run_phase3_task` (queue `llm`).
- `scripts/kickoff.py` — `--through {1,2,3}` flag chains Phase 0→1→2→3 inline.
- `src/db/run_state.py` — added `update_target_validation` + `update_target_routing`.

---

## Tooling status
**fpocket 4.0 is now installed** (built from source → `~/.local/bin/`, on PATH; suite =
fpocket/mdpocket/dpocket/tpocket). Verified end-to-end through `pockets.py` on HSP90
(1UYD): top pocket druggability 0.855, volume ~1410 Å³ → `pocket_detection="fpocket"`.
No conda/`rxdis` env exists on this machine and fpocket doesn't need one (standalone C
binary called via subprocess).

Still **not installed**: OpenMM/pdbfixer, biopython, xgboost/shap/sklearn, duckdb.
Consequences, all explicitly flagged in output (`pocket_detection`, `modifiers_applied`):

1. **Physical pocket detection now real (fpocket).** When a structure (PDB/AFDB) is
   available, `pockets.py` runs fpocket and parses per-pocket Drug Score + volume. Only
   when fpocket is absent OR no structure resolves does it fall back to the OT
   tractability proxy (`pocket_detection="tractability_proxy"`). **Cryptic-pocket MD
   (OpenMM, 50 ns implicit) is still a TODO** — so the KRAS-G12C switch-II *cryptic*
   pocket specifically still needs OpenMM; standard surface pockets are now detected.
2. **No trained XGBoost+GradientSHAP.** `scoring.py` uses a transparent linear additive
   surrogate — `weight × feature` contributions ARE the attributions. Single swap point
   when xgboost/shap land (same I/O contract).
3. **GTEx local parquet is sample-level** (no tissue annotations shipped) → HPA per-gene
   RNA tissue specificity is the primary safety source instead of GTEx tissue medians.
4. **ESMFold/AF3** only fire with `NIM_API_KEY` / AF Server cookie; otherwise PDB+AFDB only.

## Corrected scientific bug (caught in review)
AlphaMissense `high_path_missense` counts predicted-pathogenic *possible* variants
(evolutionary constraint), **not** activating gain-of-function. It no longer bumps PROTAC
above SM — it's now only an edge-case flag that routes the choice to the LLM gate. This
keeps KRAS-like targets a genuine SM/PROTAC grey-zone the LLM resolves.

## Phase-3 note vs PRD 3.4
PRD 3.4 consumes a Phase-1 `clinical_stage`; Phase 1 doesn't emit it yet, so
`repurposing_priority` is derived from ChEMBL `max_phase` (4=approved→HIGH, 2/3→MEDIUM,
1→LOW_CLINICAL, else LOW) — same buckets, real data. `novelty_mode` read via `getattr`
(not yet a `RunConfig` field).

---

## How to run (next session, when no other LLM job is active)
```
.venv/bin/python scripts/kickoff.py --disease "pancreatic cancer" --abstracts 40 --targets 10 --through 3
```
Validate against M2: KRAS should be intracellular, druggable, SM/PROTAC grey-zone → P5.

## Suggested follow-ups
- Install fpocket (conda `rxdis`) → real pockets + KRAS switch-II; add covalent-handle
  detection (cysteine near pocket) for the G12C acceptance test.
- Add `clinical_stage` to Phase 1 §1.2b output and `novelty_mode` to `RunConfig`.
- Optional Supabase Storage upload of structure PDBs (currently local `output/structures/`).
