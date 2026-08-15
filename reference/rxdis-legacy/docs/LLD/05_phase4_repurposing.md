# LLD-05: Phase 4 — Drug Repurposing

**Source:** `src/phases/phase4/`  
**PRD:** `docs/PRD_phase4_repurposing.md`  
**Celery queue:** `cpu` (Vina, DB), `hosted` (DiffDock NIM, Boltz-2)  
**Input:** Phase 3 routing + Phase 2 structure/pocket + Phase 1 targets + `RunConfig`  
**Output:** `phase4_output: dict` → `phase_results.output_json` (phase=4) + `candidates` rows

---

## 1. Module Structure

```
src/phases/phase4/
├── runner.py          — per-target repurposing, writes candidates to DB
├── chembl_query.py    — ChEMBL local SQLite: known-mechanism drugs + approved library
├── primekg_query.py   — PrimeKG drug-protein KG signal
├── docking.py         — AutoDock Vina 1.2.7 pipeline (receptor prep + docking)
├── lincs_query.py     — CLUE.io L1000 reverse-signature query
└── scoring.py         — three-signal triangulation: docking + LINCS + clinical
```

---

## 2. Entry Point

```python
def run_phase4(
    run_id: str,
    config: RunConfig,
    db,
    phase1_output: dict,
    phase2_output: dict,
    phase3_output: dict,
) -> dict:
    """
    For each target with "P4_repurpose" in branches:
      run_target_repurposing(target, config, db)
    Returns phase4 output dict.
    """
```

---

## 3. Step 4.1 — Approved Drug Retrieval (`chembl_query.py`)

```python
def get_approved_drugs(symbol: str, config: RunConfig) -> Tuple[List[Drug], List[Drug]]:
    """
    Returns (tier1_known_drugs, tier2_library).
    
    Tier 1 — known mechanism drugs:
      SQLite query on chembl_35.db:
        SELECT DISTINCT cs.canonical_smiles, md.chembl_id, md.pref_name, 
               a.pchembl_value, td.pref_name as target_name,
               md.max_phase, mh.action_type
        FROM activities a
        JOIN assays ay ON a.assay_id = ay.assay_id
        JOIN target_dictionary td ON ay.tid = td.tid
        JOIN compound_structures cs ON a.molregno = cs.molregno
        JOIN molecule_dictionary md ON a.molregno = md.molregno
        LEFT JOIN mechanism mh ON md.molregno = mh.molregno
        WHERE td.pref_name LIKE '%{symbol}%'
          AND a.pchembl_value >= 6.0
          AND md.max_phase >= 2
        ORDER BY md.max_phase DESC, a.pchembl_value DESC
        LIMIT 50
    
    Tier 2 — full approved library:
      WHERE md.max_phase = 4  (approved drugs only)
      No target filter — full FDA-approved library (~3000 compounds)
    
    Apply config.exclude_drugs: remove matching chembl_id or drug name.
    """

@dataclass
class Drug:
    chembl_id: str
    name: str
    smiles: str
    max_phase: int
    pchembl_value: Optional[float]
    action_type: Optional[str]      # "INHIBITOR" | "AGONIST" | ...
    tier: int                        # 1 = known mechanism, 2 = library
```

---

## 4. Step 4.2 — LINCS Reverse-Signature Query (`lincs_query.py`)

```python
def query_lincs_reversal(
    disease_signature: dict,    # {"up": List[str], "down": List[str]}
    config: RunConfig,
) -> List[LincsHit]:
    """
    disease_signature:
      If config.patient_cohort.expression_matrix is set:
        → compute DE genes from user data (limma-style rank product)
      Else:
        → fetch from public CREEDS/GEO via Enrichr API (disease_name search)
      Keep top 150 up, top 150 down.

    CLUE.io query:
      POST https://api.clue.io/api/sigs
      Headers: {"user_key": CLUE_API_KEY}
      Body: {"q": {"pert_type": "trt_cp"}, "fields": ["pert_id", "pert_iname", "tau"]}
      
      Compute connectivity score (CS) vs disease signature.
      Negative tau = reversal (drug effect is opposite to disease effect).
      Keep: tau < -90 (strong reversal).

    Cross-check with DrugBank approved list.
    Returns: List[LincsHit(drug_name, chembl_id, tau, plausible_mechanism)]
    """

@dataclass
class LincsHit:
    drug_name: str
    chembl_id: Optional[str]
    tau: float              # connectivity score, negative = reversal
    approved: bool
```

**LLM gate `4.2_lincs_crosscheck`:**
```
For each LINCS hit with tau < -90:
Prompt: "Drug {drug_name}, mechanism: {action_type}.
         Disease: {disease_name}. Target: {symbol}.
         LINCS reversal tau: {tau:.1f}.
         Is this mechanistically plausible? Consider off-target relevance,
         CNS penetration if needed, known contraindications."
Output schema: {
  "drug": "...", "plausible": bool, "concerns": [...], "feasibility": "high|medium|low"
}
Fallback: plausible=True for all hits with tau < -90
```

---

## 5. Step 4.3 — Virtual Screening (`docking.py`)

### Receptor preparation

```python
def prepare_receptor(
    pdb_path: str,
    output_pdbqt: str,
) -> str:
    """
    1. pdbfixer: add missing residues, add H, repair gaps.
    2. mk_prepare_receptor.py (meeko 0.7.1):
       subprocess: python mk_prepare_receptor.py -i {pdb_path} -o {output_pdbqt}
    3. Compute docking box:
       - pocket residues → centroid = center_x, center_y, center_z
       - box_size = max(22, pocket_volume_A3^(1/3) * 1.5) capped at 35 Å
    Returns: path to receptor PDBQT
    """

def prepare_ligand(smiles: str, output_pdbqt: str) -> Optional[str]:
    """
    1. RDKit: AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
    2. meeko MoleculePreparation: write PDBQT
    Returns: path or None if 3D embed fails
    """
```

### Docking execution

```python
def dock_compound(
    receptor_pdbqt: str,
    ligand_pdbqt: str,
    center: Tuple[float, float, float],
    box_size: float,
    exhaustiveness: int,    # 8 for tier1, 4 for tier2 library
) -> Optional[float]:
    """
    subprocess: ~/.local/bin/vina
      --receptor {receptor_pdbqt}
      --ligand {ligand_pdbqt}
      --center_x {x} --center_y {y} --center_z {z}
      --size_x {s} --size_y {s} --size_z {s}
      --exhaustiveness {exhaustiveness}
      --out {output_pdbqt}
    Parse stdout: first "REMARK VINA RESULT" line → score in kcal/mol
    Returns: best_affinity (most negative) or None if docking fails
    """

def run_parallel_docking(
    compounds: List[Drug],
    receptor_pdbqt: str,
    pocket: dict,
    config: RunConfig,
) -> List[Tuple[Drug, float]]:
    """
    ThreadPoolExecutor(max_workers=P4_WORKERS, default=4).
    Returns sorted list (most negative score first).
    Vina threshold: keep score < -8.0 (or -7.0 if relaxed).
    """
```

### DiffDock-V2 NIM rescoring (optional)

```python
def rescore_diffdock(
    receptor_pdb: str,
    top_compounds: List[Drug],    # top 200 from Vina
    nim_api_key: str,
) -> Dict[str, float]:
    """
    POST to NIM DiffDock-V2 endpoint.
    Returns: {chembl_id: diffdock_affinity_kcal_mol}
    Only called if NIM_API_KEY set.
    """
```

### Boltz-2 affinity (optional)

```python
def predict_boltz2_affinity(
    receptor_fasta: str,
    top_compounds: List[Drug],    # top 50 from DiffDock
    neurosnap_api_key: str,
) -> Dict[str, float]:
    """
    POST to Neurosnap Boltz-2 endpoint.
    Returns: {chembl_id: log_uM}  — lower = more potent
    Gate: keep if log_uM < 1.0 (sub-10 µM)
    Only called if NEUROSNAP_API_KEY set.
    """
```

---

## 6. Step 4.4 — PrimeKG Signal (`primekg_query.py`)

```python
def get_kg_score(symbol: str, drug_name: str) -> float:
    """
    Load Databases/primekg/edges.csv (cached on first call).
    Look up edges where:
      source_type == "drug" AND target_type == "gene/protein"
      source_name LIKE drug_name AND target_name == symbol
    Edge relation types: "drug_protein", "carrier", "enzyme", "target", "transporter"
    KG score = 1.0 if direct edge exists, 0.5 if second-degree (via disease node)
    Returns: float in [0, 1]
    """
```

---

## 7. Step 4.5 — Triangulation Scoring (`scoring.py`)

```python
def compute_repurposing_score(
    vina_score: float,           # kcal/mol, negative
    lincs_tau: Optional[float],  # negative = reversal; None if no LINCS hit
    max_phase: int,              # ChEMBL max_phase for this drug-target pair
    kg_score: float,             # PrimeKG signal
    config: RunConfig,
) -> float:
    """
    docking_norm = min(1.0, abs(vina_score) / 12.0)  # normalize: -12 kcal/mol → 1.0
    lincs_norm   = abs(lincs_tau) / 100.0 if lincs_tau is not None else 0.0
    clinical_norm = max_phase / 4.0

    repurposing_score = (
        0.40 * docking_norm +
        0.35 * lincs_norm +
        0.25 * (0.5 * clinical_norm + 0.5 * kg_score)
    )
    return min(1.0, repurposing_score)
    """
```

**LLM gate `4.4_repurposing_narrative`:**
```
For each top-k candidate:
Prompt: "Drug: {name}. Vina: {score} kcal/mol. Boltz-2: {log_uM} log µM.
         LINCS reversal tau: {tau}. Clinical stage: Phase {max_phase}.
         Target: {symbol} in {disease_label}.
         Write a 4-sentence repurposing case for a medicinal chemist."
Output schema: {"title": "...", "verdict": "strong|moderate|weak",
                "evidence": ["...", "..."], "risk": "..."}
Fallback: generate templated narrative from raw values
```

---

## 8. Output JSON Contract

```json
{
  "repurposing": {
    "TGFB1": [
      {
        "drug": "niclosamide",
        "chembl_id": "CHEMBL483",
        "vina": -9.5,
        "diffdock_score": -9.8,
        "boltz2_log_uM": 0.3,
        "lincs_tau": -88,
        "max_phase": 4,
        "kg_score": 0.5,
        "repurposing_score": 0.72,
        "narrative": {"title": "...", "verdict": "strong", "evidence": [...], "risk": "..."}
      }
    ]
  },
  "n_targets_screened": 14,
  "n_candidates_total": 32,
  "wall_time_s": 3600
}
```

---

## 9. DB Writes

```
phase_results: phase=4, running → completed
candidates: one row per (target, drug) pair that passes threshold
            kind="repurposing"
            target_id = symbol (text)
            identifier = chembl_id
            smiles = canonical_smiles
            combined_score = repurposing_score
            subscores = {vina, diffdock, boltz2_log_uM, lincs_tau, max_phase, kg_score}
decisions: gate="4.2_lincs_crosscheck", gate="4.4_repurposing_narrative"
compute_log: step="vina_docking" service="local_cpu" cost_usd=0 wall_time_s
             step="diffdock_nim" service="NIM" cost_usd~=0.005/compound
             step="boltz2" service="neurosnap" cost_usd~=0.02/compound
```

---

## 10. Failure / Recovery

| Failure | Recovery |
|---|---|
| Zero candidates > 0.5 | Mark "no_obvious_repurposing_path"; rely on P5/P6 |
| LINCS no reversal signal | Score with docking + clinical only; note in narrative |
| NIM throttled / unavailable | Reroute DiffDock to Neurosnap; or skip rescoring |
| No approved drugs for target | Skip clinical signal; run docking on full FDA library |
| Vina binary not found | Hard error: `~/.local/bin/vina` not on PATH |
| Ligand 3D embed fails (RDKit) | Skip that compound; log smiles |
| Box size computation error | Fallback: box_size = 22 Å centered on target COM |

---

## 11. Performance Characteristics

| Step | Typical time (4 cores) | Notes |
|---|---|---|
| Tier 1 Vina (50 drugs, exhaustiveness=8) | ~8 min | ~10s/compound |
| Tier 2 Vina (3000 library, exhaustiveness=4) | ~4h | Cap: P4_MAX_LIBRARY |
| DiffDock NIM (200 compounds) | ~20 min | API-dependent |
| Boltz-2 (50 compounds) | ~15 min | API-dependent |
| LINCS query | ~2 min | API latency |
