# LLD-03: Phase 2 — Target Validation (In Silico)

**Source:** `src/phases/phase2/`  
**PRD:** `docs/PRD_phase2_target_validation.md`  
**Scientific Protocol:** `Scientific Protocol/phase2_phase3_target_validation_modality_selection.md`  
**Celery queues:** `cpu`, `hosted` (NIM/Modal), `llm`  
**Input:** Phase 1 `ranked_targets` + `RunConfig`  
**Output:** `phase2_output: dict` → `phase_results.output_json` (phase=2) + updated `targets` rows

---

## 1. Module Structure

```
src/phases/phase2/
├── runner.py          — orchestrates per-target validation, writes DB
├── structure.py       — structure acquisition routing (PDB → AFDB → ESMFold → AF3)
├── pockets.py         — fpocket + PockDrug + druggability scoring
├── essentiality.py    — DepMap Chronos + ProteomeLM-Ess (Modal)
├── variants.py        — AlphaMissense lookup + AlphaGenome
├── localization.py    — HPA REST + DeepTMHMM + IUPred3
├── tractability.py    — Open Targets tractability + rule engine
└── scoring.py         — XGBoost final validation_score + GradientSHAP
```

---

## 2. Entry Point

```python
def run_phase2(
    run_id: str,
    config: RunConfig,
    db,
    phase1_output: dict,
) -> dict:
    """
    Iterates over phase1_output["ranked_targets"].
    Returns phase2_output dict with validated_targets list.
    Processes targets in parallel (ThreadPoolExecutor, max_workers=4).
    """
```

### Per-target pipeline

```
for each target in ranked_targets:
  2.1  essentiality.run(target, config)         → EssentialityResult
  2.2  structure.acquire(target, config)        → StructureResult
  2.3  pockets.detect_and_score(structure, config) → List[PocketResult]
  2.4  variants.lookup(target, config)          → VariantResult
  2.5  ppi.validate(target, config)             → PPIResult
  2.6  if disordered/membrane/dark: subroutine
  2.7  localization.query(target, config)        → LocalizationResult
  2.8  tractability.assess(target, all_results, config) → ModalityScores
  2.9  scoring.compute_validation_score(all_results) → (validation_score, shap_vals)
  → assemble evidence trail, write to DB
```

---

## 3. Step 2.1 — Essentiality (`essentiality.py`)

```python
@dataclass
class EssentialityResult:
    chronos_median: float        # DepMap: negative = essential
    is_core_essential: bool      # chronos_median < -1.0 across >80% cell lines
    selective_fraction: float    # fraction of cancer lines with chronos < -0.5
    loeuf: Optional[float]       # LOEUF from gnomAD if available
    modal_ess_score: Optional[float]  # ProteomeLM-Ess, loaded via Modal

def run_essentiality(symbol: str, config: RunConfig) -> EssentialityResult:
    """
    1. Load DepMap CRISPRGeneEffect.csv (pandas, cached in module dict after first read).
       Column = gene symbol (e.g. "KRAS (3845)") — parse symbol before parenthesis.
    2. chronos_median = median across all cell lines.
    3. is_core_essential = (chronos_median < -1.0 AND fraction_lines_below_minus1 > 0.8)
    4. If indication_type != "oncology" AND is_core_essential → set high_tox_flag=True
       (-25% penalty applied in scoring.py).
    5. Optional: ProteomeLM-Ess via Modal (if MODAL_TOKEN set and non-oncology target).
    """
```

---

## 4. Step 2.2 — Structure Acquisition (`structure.py`)

```python
@dataclass
class StructureResult:
    source: str              # "PDB" | "AFDB" | "ESMFold" | "AF3" | "OmegaFold"
    pdb_id: Optional[str]    # e.g. "6OIM" for PDB
    uniprot_id: str
    pdb_local_path: str      # path in Supabase Storage: runs/{run_id}/structure/...
    median_plddt: float
    low_confidence: bool     # True if median_plddt < 70
    domain_ranges: Optional[List[Tuple[int, int]]]  # confident residue ranges

def acquire_structure(symbol: str, uniprot_id: str,
                      run_id: str, config: RunConfig) -> StructureResult:
    """
    Routing order (tries each until success):
    1. RCSB PDB REST: search by UniProt accession, identity >= 95%
       → download CIF, convert to PDB via biopython
    2. AlphaFold DB: GET https://alphafold.ebi.ac.uk/files/AF-{uniprot}-F1-model_v4.pdb
    3. ESMFold NIM: POST to NIM endpoint with FASTA sequence
       (requires NIM_API_KEY)
    4. AlphaFold Server (AF3): for complexes; requires session
    5. OmegaFold / Boltz-1: fallback for highly dynamic proteins

    After download:
    - Run pdbfixer to add missing atoms/H
    - Compute per-residue pLDDT from B-factor column (for AFDB/ESMFold)
    - Upload PDB to Supabase Storage
    - If median_plddt < 70: set low_confidence=True, trigger 2.6 subroutine
    - LLM gate 2.2_plddt_domains if pLDDT variance high (mixed confident/uncertain)
    """
```

**LLM gate `2.2_plddt_domains`:**
```
When: median_plddt in [60, 80) AND pLDDT range > 30 (mixed structure)
Prompt: "UniProt {id}, per-residue pLDDT histogram: {histogram}.
         Known functional domains: {pfam_domains}.
         Identify ordered residue ranges, disordered ranges,
         and whether the functional domain is in an ordered region.
         Suggest structure strategy."
Output schema: {
  "ordered_ranges": [[start, end], ...],
  "disordered_ranges": [[start, end], ...],
  "functional_domain_ordered": bool,
  "strategy": "use_domain_only" | "esm_fold" | "consider_protac"
}
Fallback: ordered_ranges = [(1, len)] if pLDDT > 70 else []
```

---

## 5. Step 2.3 — Pocket Detection (`pockets.py`)

```python
@dataclass
class PocketResult:
    pocket_id: str           # "P1", "P2", ...
    druggability_score: float  # 0–1, from fpocket + PockDrug
    volume_A3: float
    depth_score: float       # fpocket drug_score
    hydrophobicity: float
    is_cryptic: bool         # found by implicit MD / P2Rank, not static structure
    strategy: str            # "competitive" | "allosteric" | "covalent" | "interface"
    residues: List[int]      # pocket residue indices

def detect_and_score_pockets(
    structure: StructureResult,
    config: RunConfig,
) -> List[PocketResult]:
    """
    1. Run fpocket on local PDB file:
       subprocess: fpocket -f {pdb_path}
       Parse fpocket output CSV: drug_score, volume, hydrophobicity per pocket.
    2. PockDrug-Server (optional, browser automation via httpx/requests):
       POST PDB → parse druggability score per pocket.
    3. CASTp cross-check (optional): compare pocket volumes.
    4. Cryptic pocket detection (if static druggability < 0.5):
       - OpenMM 50 ns implicit solvent MD (local, ~2h)
         OR P2Rank / Neurosnap API
       → compute fpocket on MD snapshots at 10 ns intervals
       → pocket appearing in ≥ 3/5 snapshots = cryptic
    5. Membrane targets: restrict fpocket to extracellular domain
       (residue range from OPM boundaries, looked up by PDB ID).
    6. max_druggability = max(pocket.druggability_score)
    7. If max_druggability < 0.5 AND no cryptic → disable_sm_branch = True
    8. LLM gate 2.3_pocket_selection if multiple pockets with score within 0.1
    """
```

**LLM gate `2.3_pocket_selection`:**
```
When: ≥ 2 pockets with |score_a - score_b| < 0.1
Prompt: "Target {symbol}. Pockets: {pocket_summaries with volume/druggability/residues}.
         Known mutations affecting function: {am_high_path_residues}.
         Which pocket is most therapeutically relevant for {disease_label}?
         Consider: mutation hotspots, known ligand sites, PPI interfaces."
Output schema: {"selected_pocket": "P1", "reason": "...", "strategy": "allosteric"}
Fallback: select highest-druggability pocket
```

---

## 6. Step 2.4 — Variant Analysis (`variants.py`)

```python
@dataclass
class VariantResult:
    high_path_missense: int     # AlphaMissense score ≥ 0.8 variants in gene
    pathogenic_fraction: float  # fraction of missense ≥ 0.8
    disease_segregating: bool   # ≥ 3 high-path variants in known disease GWAS loci
    am_hotspot_residues: List[int]  # residue positions with AM ≥ 0.8

def lookup_variants(symbol: str, ensembl_id: str, config: RunConfig) -> VariantResult:
    """
    Local AlphaMissense lookup from Databases/alphamissense/AlphaMissense_hg38.tsv.
    (File is ~7 GB — loaded on first call, cached as parquet subset per gene.)
    Filter: ENSG == ensembl_id, am_pathogenicity >= 0.8.
    disease_segregating: cross-reference with GWAS Catalog loci (genetic_evidence.py).
    Score boost: disease_segregating AND high_path_missense >= 3 → +10% in scoring.py
    """
```

---

## 7. Step 2.5 — PPI Validation (`ppi_network.py` reused)

```python
def validate_ppi(
    symbol: str,
    config: RunConfig,
    string_graph: nx.Graph,
) -> PPIResult:
    """
    1. STRING confidence score for target.
    2. ProteomeLM-PPI via Modal (if MODAL_TOKEN): predicted PPI confidence.
    3. selectivity_target anti-target: add to off_target_hazard list.
    SwissTargetPrediction: deferred to Phase 5 when SMILES is available.
    """

@dataclass
class PPIResult:
    string_confidence: float
    string_degree: int
    off_target_hazard: List[str]   # includes selectivity_target
    modal_ppi_score: Optional[float]
```

---

## 8. Step 2.6 — Disordered / Membrane / Dark Subroutine

```python
def run_special_subroutine(
    symbol: str,
    structure: StructureResult,
    config: RunConfig,
) -> SubroutineResult:
    """
    Triggered when ANY of: median_pLDDT < 70, >40% disordered,
    DeepTMHMM positive, or tdl == "Tdark"

    Disordered path:
      - Run IUPred3 (local CLI) on sequence → per-residue disorder score
      - Identify ordered regions (IUPred3 < 0.5)
      - Consider PROTAC if intracellular + any ordered domain present

    Membrane path:
      - Extract extracellular domain residues (from OPM / DeepTMHMM output)
      - Re-run fpocket on ECD only

    Tdark path:
      - Query ARCHS4 co-expression for functional clues
      - Flag as "speculative" in evidence_trail
    """
```

---

## 9. Step 2.7 — Tissue Expression & Safety (`localization.py`)

```python
@dataclass
class LocalizationResult:
    compartment: str          # "Extracellular" | "Intracellular" | "Membrane"
    is_membrane: bool
    is_secreted: bool
    critical_tissue_flag: bool  # heart/brain/kidney TPM > 10
    tsi: float                  # tissue specificity index (Jensen/HPA)
    tissue_specificity: str     # "broad" | "selective" | "tissue_restricted"

def query_localization(symbol: str, config: RunConfig) -> LocalizationResult:
    """
    1. HPA REST: GET /api/search?q={symbol} → subcellular_location, tissue_expression
    2. GTEx: load tissue-median TPM (from precomputed Databases/gtex/tissue_medians.parquet)
       - tissue_of_interest column from config
       - critical tissues: Heart, Brain, Kidney
    3. DeepTMHMM: POST FASTA to deeptmlhm.dtu.dk API → transmembrane topology
    4. TSI = 1 - (entropy of tissue expression / log2(n_tissues))
    """
```

---

## 10. Step 2.8 — Tractability Assessment (`tractability.py`)

```python
@dataclass
class ModalityScores:
    SM: float
    PROTAC: float
    AB: float
    peptide: float
    oligo: float
    primary_recommendation: str
    key_reasoning: str

def assess_tractability(
    symbol: str,
    pocket_results: List[PocketResult],
    essentiality: EssentialityResult,
    localization: LocalizationResult,
    ot_tractability: dict,        # from open_targets.py (list of {modality, label, value})
    config: RunConfig,
    llm_provider,
) -> ModalityScores:
    """
    Rule engine:
      SM_score = 0.8*max_druggability + 0.2*chembl_max_phase_norm
                 (if max_druggability > 0.5 AND chembl has chemical matter)
      PROTAC_score = 0.7 if (intracellular AND (has_weak_binder OR E3_proximity))
      AB_score = 0.85 if extracellular OR (membrane AND ECD present)
      peptide_score = 0.75 if PPI_use_case OR small_extracellular
      oligo_score = 0.6 if intracellular_undruggable AND mRNA_detectable

    Edge cases → LLM gate 2.8_tractability_edge:
      - Gain-of-function mutation (dominant oncogene) → prefer degradation (PROTAC)
      - Borderline druggability [0.45, 0.55] → ambiguous SM/PROTAC
      - Disordered + any ordered domain → PROTAC vs SM

    Open Targets tractability (list of {modality, label, value}):
      Parse: modality in {"Small molecule", "Antibody"} → normalize to SM/AB score adjustment
    """
```

**LLM gate `2.8_tractability_edge`:**
```
When: any two modality scores within 0.15 of each other
      OR gain-of-function flag in variants
      OR druggability in [0.45, 0.55]
Prompt: "Target: {symbol}. Druggability: {max_druggability}.
         Localization: {compartment}. Essentiality: {chronos_median}.
         Gain-of-function mutations: {gof_flag}.
         Open Targets tractability data: {ot_tractability}.
         Modality scores: SM={SM}, PROTAC={PROTAC}, AB={AB}.
         Choose primary modality with brief reasoning."
Output schema: {SM, PROTAC, peptide, AB, oligo, primary_recommendation, key_reasoning}
Fallback: argmax of computed scores
```

---

## 11. Step 2.9 — Aggregate Validation Score (`scoring.py`)

```python
def compute_validation_score(
    symbol: str,
    essentiality: EssentialityResult,
    structure: StructureResult,
    pockets: List[PocketResult],
    variants: VariantResult,
    localization: LocalizationResult,
    ppi: PPIResult,
    p1_evidence: dict,           # from phase1 evidence_trail
    config: RunConfig,
) -> Tuple[float, dict]:
    """
    XGBoost classifier trained on DepMap labels:
      Features: string_centralities, Node2Vec distance to known_positives,
                essentiality, druggability, variant load, tissue_specificity
      → calibrated validation_score in [0, 1]
    GradientSHAP attributions for top features.

    Thresholds:
      validation_score >= 0.5  → passes
      < 0.5 but seeded        → passes with seeded=True flag
      < 3 targets pass 0.5    → lower threshold to 0.3, warn

    Indication-type adjustments:
      oncology:   selective_essentiality weight +0.10
      chronic:    critical_tissue_flag penalty -0.25
      acute:      safety weight halved
    """
```

**LLM gate `2.9_shap_narrative`:**
```
When: always (summarises the SHAP explanation for the UI)
Prompt: "Target {symbol}. Top SHAP drivers: {top_5_shap_values}.
         Validation score: {validation_score:.2f}.
         Write a 3-sentence evidence summary for a medicinal chemist."
Output schema: {"summary": "..."}
Fallback: "Validated with score {validation_score:.2f} based on {top_feature}."
```

---

## 12. Output JSON Contract

```json
{
  "validated_targets": [
    {
      "symbol": "TGFB1",
      "validation_score": 0.79,
      "seeded": false,
      "structure": {
        "source": "AFDB", "uniprot": "P01137", "median_plddt": 88.2,
        "low_confidence": false, "pdb_local_path": "runs/.../structure/TGFB1.pdb"
      },
      "pockets": [
        {"id": "P1", "druggability": 0.71, "volume_A3": 580, "strategy": "interface",
         "is_cryptic": false}
      ],
      "essentiality": {
        "chronos_median": -0.2, "is_core_essential": false, "loeuf": 0.42,
        "high_tox_flag": false
      },
      "variants": {"high_path_missense": 14, "pathogenic_fraction": 0.43,
                   "am_hotspot_residues": [47, 89, 112]},
      "safety": {"critical_tissue_flag": false, "tsi": 0.61, "tissue_specificity": "selective"},
      "modality": {
        "SM": 0.7, "AB": 0.85, "peptide": 0.75, "PROTAC": 0.3,
        "primary": "AB", "secondary": "peptide"
      },
      "shap": {"druggability": 0.18, "eigenvector": 0.14, "gwas": 0.12},
      "evidence_summary": "TGFB1 is a secreted cytokine with a well-defined binding interface..."
    }
  ],
  "n_total": 20,
  "n_passing": 14,
  "threshold_used": 0.5,
  "wall_time_s": 840
}
```

---

## 13. DB Writes

```
phase_results: phase=2, running → completed
               output_json = validated_targets dict
targets: UPDATE each row → validation_score, modality_primary, modality_secondary,
         evidence_trail (merged with Phase 1 evidence_trail via JSON merge)
decisions: gate="2.2_plddt_domains", "2.3_pocket_selection",
           "2.8_tractability_edge", "2.9_shap_narrative" (per target)
compute_log: step="structure_acquisition" service=PDB/AFDB/ESMFold/AF3
             step="fpocket" service="local"
             step="cryptic_pockets" service="openMM/P2Rank"
```

---

## 14. Failure / Recovery

| Failure | Recovery |
|---|---|
| pLDDT < 70 throughout | 2.6 subroutine; restrict analysis to ordered fragments |
| All pockets undruggable | Disable SM branch; force peptide/biologic (P6) and/or PROTAC |
| AF Server quota hit | ESMFold NIM for non-complex; park AF3 |
| Tdark gene, zero functional info | Flag "very speculative"; pass if seeded |
| < 3 targets pass threshold | Lower threshold to 0.3, warn in output |
| DepMap gene name mismatch | Try stripping parenthetical Entrez ID from column header |
| RCSB PDB down | Skip to AFDB directly |
