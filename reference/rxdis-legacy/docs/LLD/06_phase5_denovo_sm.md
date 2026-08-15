# LLD-06: Phase 5 — De Novo Small Molecule Design

**Source:** `src/phases/phase5/`  
**PRD:** `docs/PRD_phase5_denovo_small_molecule.md`  
**Scientific Protocol:** `Scientific Protocol/phase5_denovo_small_molecule.md`  
**Celery queue:** `cpu` (RDKit), `gpu` (REINVENT4), `hosted` (NIM, Neurosnap, RunPod)  
**Input:** Phase 3 routing + Phase 2 pocket/structure + `RunConfig`  
**Output:** `phase5_output: dict` → `phase_results.output_json` (phase=5) + `candidates` rows

---

## 1. Module Structure

```
src/phases/phase5/
├── runner.py        — per-target pipeline, writes candidates to DB
├── fragment_gen.py  — REINVENT4 Mol2Mol (subprocess) + BRICS fallback
├── filters.py       — Ro5, Veber, PAINS, SA, QED, Tanimoto novelty
├── admet.py         — local RDKit ADMET: hERG/AMES/hepatox/BBB/caco2/logS
└── scoring.py       — combined_pre8 formula
```

---

## 2. Entry Point

```python
def run_phase5(
    run_id: str,
    config: RunConfig,
    db,
    phase1_output: dict,
    phase2_output: dict,
    phase3_output: dict,
) -> dict:
    """
    For each target with "P5_small_molecule" in branches:
      run_target_denovo_sm(target, config, db)
    Returns phase5 output dict.
    """
```

---

## 3. Step 5.1 — Pocket-Targeted Library Screen

```python
def screen_enamine_library(
    receptor_pdbqt: str,
    pocket: dict,
    config: RunConfig,
) -> List[str]:
    """
    Screens Enamine REAL Diverse Drug-Like slice (~5M compounds, ~5 GB).
    
    Local path: Databases/enamine/enamine_real_druglike.smi (one SMILES per line)
    
    Strategy:
      If RUNPOD_API_KEY set:
        Upload receptor + subset to RunPod A100 job
        → QuickVina-W on full 5M, ~3h, ~$3
      Else:
        Random sample 100K from Enamine REAL
        → AutoDock Vina local on 100K, exhaustiveness=4
    
    Pre-filter before docking (RDKit):
      MW in [150, 500], logP in [-2, 5], HBD ≤ 5, HBA ≤ 10
      (quick Ro5 to reduce docking queue)
    
    Keep: Vina score < -8.0 AND RMSD across 3 poses < 2 Å (pose stability check)
    Returns: top 1000 SMILES sorted by docking score
    """
```

---

## 4. Step 5.2 — De Novo Generation (`fragment_gen.py`)

```python
def generate_molecules(
    receptor_pdbqt: str,
    pocket: dict,
    seed_smiles: List[str],      # from P4 hits or config.seed_smiles
    config: RunConfig,
    n_molecules: int = 5000,
) -> List[str]:
    """
    If config.seed_smiles set for this target:
      SKIP generation → return config.seed_smiles (optimization-only mode)
    
    Generation preference order:
      1. REINVENT4 (local GPU, LibInvent/Mol2Mol)
      2. GenMol NIM (cloud)
      3. BRICS fragmentation fallback (CPU, always available)
    """

def _generate_reinvent4(
    seed_smiles: List[str],
    receptor_pdbqt: str,
    pocket: dict,
    n_molecules: int,
) -> List[str]:
    """
    Writes a TOML config file for REINVENT4:
      [parameters]
      model_type = "Mol2Mol"
      smiles = [seed_smiles...]
      scoring = [{name="QED"}, {name="SA"}, {name="DockingScore",
                  receptor=receptor_pdbqt, center_x=..., size_x=...}]
      batch_size = 100     # conservative for 6 GB GPU
      num_steps = 500
    
    Subprocess: reinvent {config_toml} --output {output_csv}
    Parse CSV: keep SMILES from rows with total_score > 0.4
    Falls back to BRICS if reinvent binary not on PATH.
    Peak VRAM: ~6 GB (tight on RTX 3050, batch_size=100 mitigates OOM)
    """

def _generate_brics_fallback(
    seed_smiles: List[str],
    n_molecules: int,
) -> List[str]:
    """
    Uses RDKit BRICS.BRICSDecompose + BRICSBuild:
      1. Decompose each seed into fragments at BRICS bond breakage points
      2. Enumerate combinations of fragments → novel molecules
      3. Deduplicate by canonical SMILES
    Always available (pure RDKit, no GPU).
    """
```

---

## 5. Step 5.3 — Filtering (`filters.py`)

```python
def apply_filters(
    smiles_list: List[str],
    config: RunConfig,
    reference_smiles: Optional[List[str]] = None,   # ChEMBL approved for novelty
) -> List[str]:
    """
    Sequential filter pipeline (drop-first-fail):
    
    1. PAINS: RDKit FilterCatalog(PAINS) — pan-assay interference compounds
    2. Lipinski Ro5: MW ≤ 500, logP ≤ 5, HBD ≤ 5, HBA ≤ 10
    3. Veber: rotatable bonds ≤ 10, TPSA ≤ 140
    4. Egan: logP ≤ 5.88, TPSA ≤ 131.6
    5. REOS: MW [200, 500], logP [-5, 5], HBD [0, 5], HBA [0, 10],
             formal charge [-2, 2], rotatable bonds [0, 8]
    6. SA score: RDKit SA_Score ≤ 6.0 (synthesizability)
    7. QED: RDKit QED.qed ≥ 0.3
    8. Tanimoto novelty vs ChEMBL approved:
       Morgan FP radius=2 (new RDKit MorganGenerator API)
       Keep if max(Tanimoto vs all approved) < 0.4
       (unless intentional analog — seed_smiles mode skips this check)
    
    Returns filtered list (~200–500 molecules expected from 5K input).
    """

def _compute_morgan_fp(smiles: str, radius: int = 2, n_bits: int = 2048):
    """Uses rdkit.Chem.rdMolDescriptors.GetMorganFingerprintAsBitVect (new API)."""
```

---

## 6. Step 5.4 — ADMET Prediction (`admet.py`)

```python
@dataclass
class ADMETResult:
    herg_risk: str          # "low" | "medium" | "high"
    ames_positive: bool
    hepatotox_risk: str
    bbb_penetrant: Optional[bool]   # None if non-CNS indication
    caco2_perm: str         # "low" | "medium" | "high"
    logs: float             # aqueous solubility log(mol/L)
    mw: float
    logp: float
    tpsa: float
    hbd: int
    hba: int
    disqualifying_flags: List[str]

def predict_admet(smiles: str, config: RunConfig) -> ADMETResult:
    """
    All predictions are local RDKit SMARTS + descriptor rules.
    No external API calls. Instant (< 1 ms per compound).
    
    hERG: SMARTS alert for basic nitrogen + aromatic + logP > 3 → risk scoring
    AMES: SMARTS alerts for mutagenic fragments (derived from Kazius/Ames database)
    Hepatotox: SMARTS for hepatotoxic scaffold substructures
    BBB: Clark model — logP in [0, 3] AND MW < 400 AND TPSA < 90 → penetrant
         Only flagged if indication_type != "oncology" (non-CNS typically doesn't need)
    caco2: correlate with TPSA and rotatable bonds (Palm 1998 proxy)
    logS: ESOL model (Delaney 2004): logS = 0.16 - 0.63*logP - 0.0062*MW + 0.066*HBD - 0.74*rots
    
    Disqualifying logic:
      If herg_risk == "high"   → disqualifying (unless indication justifies cardiac risk)
      If ames_positive         → disqualifying
      If hepatotox_risk == "high" → disqualifying
      If BBB needed AND NOT bbb_penetrant → disqualifying
    
    selectivity_target: if set, run SwissTargetPrediction-style SMARTS matching
      → if strong hit against selectivity_target → add to disqualifying_flags
    """
```

**LLM gate `5.4_admet_context`:**
```
When: compound has 1-2 concerning (non-disqualifying) ADMET flags
Prompt: "Compound SMILES: {smiles}
         Indication: {indication_type}, disease: {disease_label}
         ADMET results: hERG={herg_risk}, AMES={ames_positive},
                        BBB={bbb_penetrant}, logS={logs:.2f}
         Patient population likely: {chronic_elderly_flag}
         Is this ADMET profile acceptable for this indication?
         Consider: cardiac risk tolerance in oncology vs chronic,
                   CNS penetration necessity."
Output schema: {
  "overall_verdict": "acceptable" | "borderline" | "disqualify",
  "disqualifying": [...],
  "concerns": [...],
  "positives": [...]
}
Fallback: disqualify if ≥ 2 critical flags; borderline if 1; acceptable if 0
```

---

## 7. Step 5.5 — Re-Dock and Rescore

```python
def redock_and_rescore(
    smiles: str,
    receptor_pdbqt: str,
    pocket: dict,
    config: RunConfig,
) -> Tuple[float, Optional[float]]:
    """
    DiffDock-V2 NIM (if NIM_API_KEY):
      Top pose affinity → diffdock_score
    Boltz-2 Neurosnap (if NEUROSNAP_API_KEY):
      Affinity prediction → boltz2_log_uM
    AF3 Server (optional, cofactor complexes):
      Only if cofactor needed for activity.
    
    Returns: (vina_score, boltz2_log_uM)
    Gate: keep if boltz2_log_uM < 1.0 (< 10 µM)
    """
```

---

## 8. Step 5.6 — Lead Optimization

```python
def run_lead_optimization(
    top_candidates: List[dict],
    receptor_pdbqt: str,
    pocket: dict,
    config: RunConfig,
) -> List[dict]:
    """
    MMP analysis:
      RDKit rdMMPA.FindMMP → matched molecular pairs
      For each MMP (transformation A→B): compute delta in Vina/QED/SA
    
    REINVENT4 LibInvent / Mol2Mol R-group:
      Bias generation toward transformations with positive delta
      5-iteration optimization loop
    
    Stop condition: NO analog improves Vina > 0.5 kcal/mol AND ADMET
                   OR iteration limit (5) reached
    """
```

**LLM gate `5.6_opt_direction`:**
```
When: after MMP analysis, before starting optimization iterations
Prompt: "Lead compound: {smiles}. Vina: {score}. ADMET: {summary}.
         Top MMP transformations found: {top5_mmps with delta values}.
         Suggest the top 3 structural modifications to pursue in next iteration.
         Consider: potency improvement, ADMET improvement, synthetic accessibility."
Output schema: {
  "modifications": [
    {"change": "add F at para position", "expected_benefit": "...",
     "risk": "...", "priority": 1}
  ]
}
Fallback: use top-3 MMPs by Vina delta
```

---

## 9. Scoring Formula (`scoring.py`)

```python
def compute_combined_pre8(
    vina_score: float,
    boltz2_log_uM: Optional[float],
    admet: ADMETResult,
    qed: float,
    tanimoto_to_approved: float,
    config: RunConfig,
) -> float:
    """
    docking_norm = min(1.0, abs(vina_score) / 12.0)
    admet_norm   = 1.0 - (len(admet.disqualifying_flags) * 0.3 + 
                           len(admet_concerns) * 0.1)
    admet_norm   = max(0.0, min(1.0, admet_norm))
    novelty_norm = 1.0 - tanimoto_to_approved
    
    combined_pre8 = (
        0.40 * docking_norm +
        0.25 * admet_norm +
        0.20 * qed +
        0.15 * novelty_norm
    )
    return min(1.0, combined_pre8)
    """
```

---

## 10. Output JSON Contract

```json
{
  "de_novo_sm": {
    "LRRK2": [
      {
        "id": "DNSM_001",
        "smiles": "CC1=NC(=CC=C1)NC2=NC(=NC=C2)NC3=CC=CC=C3",
        "vina": -10.1,
        "diffdock_score": -10.4,
        "boltz2_log_uM": 0.2,
        "qed": 0.74,
        "sa": 2.9,
        "tanimoto_to_approved": 0.31,
        "admet": {"hERG": "low", "AMES": "negative", "hepatotox": "low",
                  "BBB": true, "caco2": "high", "logS": -3.2},
        "combined_pre8": 0.81,
        "source": "reinvent4"
      }
    ]
  },
  "n_targets": 8,
  "n_candidates_total": 47,
  "wall_time_s": 7200
}
```

---

## 11. DB Writes

```
phase_results: phase=5, running → completed
candidates: one row per (target, molecule) passing all gates
            kind="de_novo_sm"
            target_id = symbol
            smiles = canonical SMILES
            combined_score = combined_pre8
            subscores = {vina, diffdock, boltz2_log_uM, qed, sa, tanimoto, admet}
            artifact_paths = [pose PDBQT path in Storage]
decisions: gate="5.3_pains_override", gate="5.4_admet_context", gate="5.6_opt_direction"
compute_log: step="enamine_screen" service="runpod/local" cost_usd
             step="reinvent4_gen" service="local_gpu"
             step="diffdock_nim" service="NIM"
```

---

## 12. Failure / Recovery

| Failure | Recovery |
|---|---|
| REINVENT4 OOM on 6 GB GPU | Reduce batch_size to 100; retry; fall back to BRICS |
| REINVENT4 binary not on PATH | BRICS fallback (always available) |
| All molecules fail ADMET | Restart 5.2 with ChEMBL scaffold seed instead of Enamine |
| Undruggable pocket | Redirect to Phase 6 (biologic); mark SM as "no viable pocket" |
| RunPod unavailable | Screen 100K subset locally instead of 5M |
| 3D embed fails for > 50% of library | Log; continue with embeddable subset |
