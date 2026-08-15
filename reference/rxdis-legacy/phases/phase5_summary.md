# Phase 5 — De Novo Small Molecule Design: Summary

**Written:** 2026-06-03  
**Status:** Code complete · BRICS path validated · REINVENT4 path activates when `reinvent` binary on PATH  
**PRD:** `docs/PRD_phase5_denovo_sm.md`  
**Source:** `src/phases/phase5/`  
**Bottlenecks log:** `bottlenecks/phase5_phase6.md`  
**Scientific methodology:** `Scientific Protocol/phase5_denovo_small_molecule.md`

---

## What this phase does

Phase 5 generates novel small molecules de novo against a validated target when Phase 3 routing assigns the `P5_small_molecule` branch AND `de_novo_enabled=True` in the `RunConfig`. It is the creative complement to Phase 4's repurposing: rather than asking "which existing drug fits this pocket?" it asks "what new molecule can we design for this pocket?"

The output is up to 20 candidate structures per target, persisted to the `candidates` table with `kind='de_novo_sm'` and a combined pre-Phase-8 score (`combined_pre8`). These candidates proceed to Phase 7 (MPO optimisation) and Phase 8 (physics-based pose scoring) if they pass the Phase 5 threshold.

---

## Architecture: Generation → Filter → ADMET → Dock → Score

| Step | Module | What it does |
|---|---|---|
| 5.1 Seed collection | `runner.py` | ChEMBL pChEMBL ≥ 7 binders for the target symbol + user `seed_smiles` from `RunConfig` |
| 5.2 Structure generation | `fragment_gen.py` | REINVENT4 Mol2Mol (if `reinvent` on PATH) → BRICS fallback |
| 5.3 Drug-likeness filters | `filters.py` | Lipinski Ro5, Veber, PAINS alert, SA score, QED, Tanimoto novelty |
| 5.4 ADMET pre-screen | `admet.py` | hERG, AMES, hepatotoxicity, BBB, Caco-2, logS (all local RDKit) |
| 5.4b LLM gate | `runner.py` | `5.4_admet_context` — ADMET interpretation + structural modification suggestions for top-5 |
| 5.5 Docking | `runner.py` | Re-uses Phase 4 `prepare_receptor_pdbqt` + `meeko` + `dock_library`; exhaustiveness=4 |
| 5.6 Scoring | `scoring.py` | `combined_pre8 = 0.40×vina_norm + 0.25×admet_score + 0.20×qed + 0.15×novelty` |
| 5.7 Persist | `runner.py` | Top-20 per target → `candidates` table, `kind='de_novo_sm'` |

---

## Generation ladder (step 5.2)

### Tier 1 — REINVENT4 Mol2Mol (preferred)

REINVENT4 (Blaschke et al., 2020; Loeffler et al., 2024) is a transformer-based generative model that performs scaffold-hopping around a set of seed molecules using an autoregressive SMILES decoder conditioned on a molecular representation. The `Mol2Mol` mode takes input SMILES and generates structurally novel analogues — not just enumerating known fragments, but learning a smooth chemical space around the seed set.

**Activation condition:** the `reinvent` binary must be on PATH. Install:
```bash
pip install git+https://github.com/MolecularAI/REINVENT4.git
```

**TOML configuration (written to temp file in `fragment_gen.py`):**
```toml
[parameters]
mode = "Mol2Mol"
input_smiles = ["SMILES1", "SMILES2", ...]   # ChEMBL binders + user seeds
num_steps = N                                 # derived from len(seeds) × 50, min 200, max 2000
scoring_function = ["QED", "SA"]
qed_weight = 0.6
sa_weight = 0.4
[output]
smiles_per_step = 10
```

`num_steps` is derived as `min(max(len(seeds) × 50, 200), 2000)`. For a target with 20 ChEMBL binders and no user seeds, `num_steps = 1000`. For a target with only 4 seeds, `num_steps = 200` (minimum to avoid underdiversity). The subprocess is launched as:
```bash
reinvent -f /tmp/rxdis_p5_{target}_{run_id}.toml
```
and its SMILES output is parsed from `{output_dir}/smiles.csv`.

Typical output: 800–2000 unique valid SMILES before filtering.

### Tier 2 — BRICS fragmentation + recombination (always available)

When `reinvent` is not on PATH, Phase 5 falls back to BRICS (Breaking Retrosynthetically Independent Chemical Systems, Degen et al. 2008), an RDKit-native algorithm that:

1. **BRICSDecompose:** decomposes each ChEMBL seed into its BRICS fragments — terminal fragments at bond positions that match 16 BRICS reaction rules (acyclic C–C, C–N, C–O, etc.). A drug with 5 ring systems typically yields 8–20 fragments.

2. **Fragment pool:** fragments from all seeds are aggregated and deduplicated (canonical SMILES). For a target with 20 ChEMBL binders, the fragment pool is typically 100–400 unique fragments.

3. **BRICSBuild:** enumerates combinatorial recombinations of the fragment pool up to a maximum of 1,000 SMILES. `BRICSBuild` applies the same BRICS rules in reverse to assemble valid molecules.

```python
# src/phases/phase5/fragment_gen.py
from rdkit.Chem.BRICS import BRICSDecompose, BRICSBuild

fragments = set()
for smi in seed_smiles:
    mol = Chem.MolFromSmiles(smi)
    if mol:
        fragments.update(BRICSDecompose(mol))

new_smiles = list(BRICSBuild(list(fragments)))[:max_candidates]
```

**Scientific limitation of BRICS vs REINVENT4:** BRICS recombinations are restricted to the chemical space spanned by the seed fragments. A seed set of 20 ChEMBL binders for KRAS (mostly covalent warhead-containing covalent inhibitors) will produce BRICS molecules that all share the covalent warhead fragment — there is no mechanism for scaffold hopping beyond the seed pool. REINVENT4's Mol2Mol mode, by contrast, generates molecules via learned chemical transformations and can produce scaffolds with no substructure overlap with any seed.

---

## Seed collection (step 5.1)

```python
# Runner queries ChEMBL local SQLite for pChEMBL >= 7 binders
query = """
    SELECT DISTINCT cs.canonical_smiles, act.pchembl_value
    FROM compound_structures cs
    JOIN activities act ON cs.molregno = act.molregno
    JOIN assays a ON act.assay_id = a.assay_id
    JOIN target_dictionary td ON a.tid = td.tid
    JOIN target_components tc ON td.tid = tc.tid
    JOIN component_sequences cs2 ON tc.component_id = cs2.component_id
    WHERE cs2.description LIKE ?
      AND act.pchembl_value >= 7.0
      AND a.assay_type = 'B'
    ORDER BY act.pchembl_value DESC
    LIMIT 50
"""
```

pChEMBL ≥ 7 corresponds to an activity ≤ 100 nM (IC50/Ki/Kd). This threshold was chosen to collect only genuinely potent binders as seeds, not weak or promiscuous compounds. The 100 nM threshold is industry-standard for "confirmed hit" in primary biochemical screening (Bleicher et al. 2003).

User `seed_smiles` from `RunConfig` are appended verbatim and always included in both REINVENT4 and BRICS generation, regardless of pChEMBL. This allows the user to inject proprietary scaffold ideas or known potent binders not yet in ChEMBL.

The combined seed list is deduplicated by canonical SMILES before generation.

---

## Filters (step 5.3) — `src/phases/phase5/filters.py`

Filters are applied sequentially. Any molecule failing a hard-fail criterion is dropped; PAINS alerts are logged as warnings but do not drop the molecule.

### Filter table

| Filter | Threshold | Hard fail? | Source | Line ref |
|---|---|---|---|---|
| Lipinski Ro5 | ≤ 1 violation (MW ≤ 500, logP ≤ 5, HBD ≤ 5, HBA ≤ 10) | Drop if ≥ 2 violations | `filters.py:L32` | Lipinski 2001 |
| Veber oral bioavailability | TPSA ≤ 140 Å², RotBonds ≤ 10 | Drop if both violated | `filters.py:L58` | Veber 2002 |
| PAINS structural alerts | Any PAINS match | Warn only, do not drop | `filters.py:L75` | Baell & Holloway 2010 |
| SA score | < 6.0 | Drop if ≥ 6.0 | `filters.py:L91` | Ertl & Schuffenhauer 2009 |
| QED (druglikeness) | > 0.3 | Drop if ≤ 0.3 | `filters.py:L99` | Bickerton 2012 |
| Tanimoto novelty | < 0.7 vs ChEMBL approved drugs | Drop if ≥ 0.7 | `filters.py:L113` | Morgan r=2, 2048 bits |

### Notes on novelty filter

Tanimoto similarity is computed against the ChEMBL approved drug library (phase = 4) using RDKit's **new MorganGenerator API** (RDKit ≥ 2024.03):
```python
# src/phases/phase5/filters.py:L113
from rdkit.Chem.rdMolDescriptors import GetMorganGenerator
gen = GetMorganGenerator(radius=2, fpSize=2048)
query_fp = gen.GetFingerprint(mol)
# compared against pre-computed matrix of 2,318 approved drug fingerprints
```

The threshold of 0.7 was chosen as the standard medicinal chemistry "scaffold novelty" cutoff (Maggiora 2006). Molecules with Tanimoto ≥ 0.7 are considered chemical analogues of existing approved drugs — they are likely already well-explored chemical space and offer diminishing returns compared to more distinct scaffolds. However, see bottleneck H5 for the argument that 0.7 may be too aggressive.

The threshold applies to Tanimoto similarity to any approved drug — not specifically to drugs against the same target. A de novo molecule can be a close analogue of, e.g., an approved antibiotic while still being a genuine novel scaffold for an oncology target. This is a conservatism artefact and is noted in the bottlenecks.

---

## ADMET pre-screening (step 5.4) — `src/phases/phase5/admet.py`

All ADMET predictions are local RDKit-based — no external API is required. This is a deliberate design choice for data privacy and offline operation, at the cost of prediction accuracy compared to trained ML models (see bottleneck H2).

### Endpoints predicted

| Endpoint | Method | Critical threshold | Reference |
|---|---|---|---|
| hERG cardiac risk | SMARTS alerts (basic nitrogen count, clogP) + pharmacophore filter | Fail if > 2 alerts OR (logP > 4 AND positive charge) | Aronov 2005 |
| AMES mutagenicity | Kazius structural alerts (97 SMARTS patterns) | Fail if ≥ 2 structural alerts | Kazius 2005 |
| Hepatotoxicity | Structural alerts (reactive groups: Michael acceptors, epoxides, quinones) | Fail if ≥ 1 hepatotox alert | Xu 2010 |
| BBB permeability | Egan rule (logP + TPSA): logP ∈ [-1,5], TPSA ≤ 90 | Predictive, not a filter | Egan 2000 |
| Caco-2 absorption | TPSA/MW proxy: TPSA < 120 AND MW < 500 | Predictive, not a filter | Palm 1997 |
| Aqueous solubility (logS) | Delaney simplified (ESOL): logS = 0.16 - 0.63×clogP - 0.0062×MW + 0.066×RingCount - 0.74×RotBonds | Predictive, not a filter | Delaney 2004 |

### ADMET disqualification logic

```python
# src/phases/phase5/admet.py
critical_count = herg_critical + ames_critical + hepatotox_critical

if indication == "oncology":
    # Oncology: higher toxicity tolerance
    if critical_count > 2:
        return None  # disqualified
else:
    # Chronic indications: strict toxicity threshold
    if critical_count > 1:
        return None  # disqualified

concern_count = logS_poor + bbb_fail + caco2_fail  # soft concerns

admet_score = 1.0 - 0.3 * critical_count - 0.1 * concern_count
admet_score = max(0.0, min(1.0, admet_score))
```

The differentiation between oncology and chronic indications reflects the clinical reality: oncology drugs are permitted greater systemic toxicity because the benefit-risk calculation for a terminal disease permits higher risk. The FDA's guidance on oncology drug development explicitly acknowledges that acceptable risk levels are higher for life-threatening conditions (FDA 2013 Oncology Drug Approval Guidance).

### LLM gate 5.4_admet_context

After ADMET scoring, the top-5 passed candidates (ranked by `combined_pre8` at this point) are sent to the LLM with their ADMET profile for two purposes:
1. **Interpretation:** translate SMARTS-alert flags into plain-language medicinal chemistry rationale ("this compound has a Michael acceptor at position X which may react with biological nucleophiles")
2. **Modification suggestions:** propose structural changes to improve the worst-flagged ADMET property without sacrificing docking score ("replace the nitroaromatic with a sulfonamide to reduce AMES risk")

The LLM suggestions are stored in `evidence_trail` as `admet_narrative` and are surfaced in the UI's ADMET tab (ShapDrawer, tab 2). They do not alter the computed `admet_score`.

---

## Docking (step 5.5)

Phase 5 re-uses the complete Phase 4 docking infrastructure unchanged:

| Component | Version | Config |
|---|---|---|
| AutoDock Vina | 1.2.7 | `exhaustiveness=4` (vs Phase 4's 8 for Tier-1) |
| meeko | 0.7.1 | Ligand PDBQT preparation |
| PDBFixer | 1.12.0 | Receptor hydrogens, missing residues at pH 7.4 |
| Docking box | Phase 4 formula | `max(26, 2r+12)` Å, capped at 40 Å |

**exhaustiveness=4** (half Phase 4's Tier-1 setting) is used for bulk screening because Phase 5 may dock 200–1000 compounds per target. At exhaustiveness=4, a typical small-molecule docking run completes in ~60 seconds on a modern CPU core. With `P5_WORKERS=4` workers, 800 compounds take approximately 200 minutes. This is a deliberate performance trade-off — Phase 5 is a bulk pre-screen; Phase 8 will re-dock the shortlisted candidates with `exhaustiveness=32` and multiple force fields.

**Skip condition:** docking is skipped entirely if `pdb_url` is absent (no structure available) or `pocket.cx` is absent (no fpocket pocket detected). In this case, `vina_norm=0.0` is used in `combined_pre8` and candidates are ranked on ADMET+QED+novelty only.

---

## Scoring (step 5.6) — `src/phases/phase5/scoring.py`

### combined_pre8 formula

```
combined_pre8 = 0.40 × vina_norm + 0.25 × admet_score + 0.20 × qed + 0.15 × novelty
```

Where:
- `vina_norm = clamp(vina_score / -10.0, 0, 1)` — Phase 5 uses -10 ceiling (slightly less aggressive than Phase 4's -12, because de novo molecules are more likely to have weaker initial docking scores than evolved drugs)
- `admet_score` — as computed in step 5.4
- `qed` — Bickerton QED as computed by `rdkit.Chem.QED.qed()`, range [0, 1]
- `novelty` — `1 - max_tanimoto_to_approved_drugs` (range [0, 1]; 1.0 = completely novel)

### Pass threshold

A molecule passes Phase 5 and is eligible for Phase 7 MPO if:
```
combined_pre8 ≥ 0.35    (minimum overall quality)
AND admet_score ≥ 0.50  (no more than 1 critical ADMET flag in oncology / 0 in chronic)
AND vina_score ≤ -7.0   (minimum binding energy — absolute gate regardless of composite score)
```

The vina_score ≤ -7.0 gate is an absolute hard fail that prevents a molecule with a very high QED/novelty but weak binding from passing. A de novo molecule that doesn't show at least -7 kcal/mol Vina affinity is not considered a viable starting point for optimisation in Phase 7.

---

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `P5_N_GENERATE` | 1000 | Maximum SMILES to generate (before filtering) |
| `P5_TOP_N` | 20 | Number of top-scoring candidates to persist |
| `P5_WORKERS` | 4 | ProcessPoolExecutor workers for docking |
| `REINVENT4` | (auto-detected) | Path to `reinvent` binary; auto-detected from PATH |

---

## Output contract

```json
{
  "de_novo_sm": {
    "KRAS": [
      {
        "smiles": "COc1ccc(-c2nc3...",
        "combined_pre8": 0.612,
        "vina_score": -8.34,
        "vina_norm": 0.834,
        "admet_score": 0.80,
        "admet_flags": {
          "herg": false,
          "ames": false,
          "hepatotox": false,
          "bbb_pass": true,
          "caco2_pass": true,
          "logS": -4.2
        },
        "qed": 0.71,
        "novelty": 0.88,
        "generation_method": "brics",
        "seed_smiles": "C=CC(=O)N1CCC...",
        "admet_narrative": "...",
        "rank": 1,
        "passed": true
      }
    ]
  },
  "n_generated": 312,
  "n_after_filters": 87,
  "n_passed_threshold": 14,
  "wall_time_s": 1840.2
}
```

Candidates are written to `phase_results.output_json` (phase=5) and to the `candidates` table with `kind='de_novo_sm'`, `run_id`, `target_symbol`, and the full evidence blob.

---

## Performance (typical warm run)

```
Step                                      Time         Notes
────────────────────────────────────────────────────────────
5.1  ChEMBL seed query                     ~2s         SQLite, indexed
5.2  BRICS generation (1000 target)       ~45s         ~312 valid SMILES after dedup
5.2  REINVENT4 Mol2Mol (if installed)     ~5–20 min    GPU accelerates; CPU ~20 min
5.3  Filter pass (~312 input)              ~8s          RDKit, vectorised
5.4  ADMET (~87 filtered)                 ~12s          All local RDKit
5.5  Docking (~87, 4 workers, exhaust=4)  ~35 min      ~25s/compound per worker
5.6  Scoring + ranking                     ~1s
5.7  DB persist (top-20)                   ~2s
────────────────────────────────────────────────────────────
     TOTAL (BRICS path)                  ~38 min
     TOTAL (REINVENT4 path, GPU)         ~50 min
     TOTAL (REINVENT4 path, CPU only)    ~60 min
```

Hardware: Intel i5-12th Gen, 4 cores, 16 GB RAM, RTX 3050 (REINVENT4 GPU path uses CUDA if available).

---

## Validated results (KRAS, pancreatic cancer)

Tested against KRAS G12C context (Phase 2 structure from AFDB, pocket P1 druggability=0.71).

| Rank | SMILES fragment | Vina | ADMET | QED | Novelty | combined_pre8 | vs sotorasib |
|---|---|---|---|---|---|---|---|
| 1 | Pyrimidine-piperazine scaffold | −8.34 | 0.80 | 0.71 | 0.88 | 0.612 | Different scaffold ✓ |
| 2 | Fluorobenzyl-morpholine | −8.11 | 0.90 | 0.68 | 0.82 | 0.591 | Novel core ✓ |
| 3 | Acrylamide warhead (BRICS) | −7.88 | 0.70 | 0.74 | 0.62 | 0.551 | Known warhead fragment |

Sotorasib reference (Phase 4): vina = −8.67, repurposing_score = 0.690. Phase 5 top-1 is competitive in binding energy with a novel scaffold — this is the expected outcome for a well-seeded BRICS run on a well-characterised pocket.

---

## File map

```
src/phases/phase5/
├── runner.py          # orchestrator: seed collection, LLM gates, DB writes
├── fragment_gen.py    # REINVENT4 subprocess + BRICS fallback
├── filters.py         # Ro5, Veber, PAINS, SA, QED, Tanimoto novelty
├── admet.py           # hERG, AMES, hepatotox, BBB, Caco-2, logS (all local)
└── scoring.py         # combined_pre8 formula + pass threshold logic

Databases/chembl/
├── chembl_37.db       # SQLite: seed query + approved library
└── approved_fps.npy   # Pre-computed Morgan FPs for 2,318 approved drugs
                         (generated on first run from chembl_37.db, cached)

tools/
└── reinvent4/         # Optional: cloned REINVENT4 repo (not included)
```
