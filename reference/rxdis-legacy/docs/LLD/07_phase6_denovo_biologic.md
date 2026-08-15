# LLD-07: Phase 6 — De Novo Biologic / Peptide Design

**Source:** `src/phases/phase6/`  
**PRD:** `docs/PRD_phase6_denovo_biologic.md`  
**Scientific Protocol:** `Scientific Protocol/phase6_denovo_biologic.md`  
**Celery queue:** `hosted` (BoltzGen/RFdiffusion NIM), `gpu` (ProteinMPNN local), `cpu` (NetMHCpan)  
**Input:** Phase 3 routing + Phase 2 structure/interface + `RunConfig`  
**Output:** `phase6_output: dict` → `phase_results.output_json` (phase=6) + `candidates` rows

---

## 1. Module Structure

```
src/phases/phase6/
├── runner.py              — per-target pipeline, orchestrates all steps
├── interface_analysis.py  — pocket/interface extraction, design strategy classification
├── peptide_gen.py         — generation ladder: BoltzGen → RFdiffusion NIM → ProteinMPNN → LLM
├── neurosnap_boltzgen.py  — Neurosnap BoltzGen API client
├── nim_rfdiffusion.py     — NVIDIA NIM RFdiffusion API client
├── proteinmpnn_runner.py  — local ProteinMPNN subprocess
└── developability.py      — aggregation, solubility, immunogenicity, stability checks
```

---

## 2. Entry Point

```python
def run_phase6(
    run_id: str,
    config: RunConfig,
    db,
    phase1_output: dict,
    phase2_output: dict,
    phase3_output: dict,
) -> dict:
    """
    For each target with "P6_biologic" in branches:
      run_target_biologic(target, config, db)
    Returns phase6 output dict.
    """
```

---

## 3. Step 6.1 — Interface Analysis (`interface_analysis.py`)

```python
@dataclass
class InterfaceContext:
    symbol: str
    pdb_url: str                      # Supabase Storage path
    target_class: str                 # "extracellular" | "intracellular" | "membrane" | "disordered"
    design_strategy: str              # see below
    hotspots: List[int]               # residue indices (AlphaMissense + fpocket contact)
    binder_length_range: Tuple[int, int]
    cyclic_preferred: bool
    compartment: str
    chronos_median: float

def extract_interface_context(
    target: dict,       # validated_target from Phase 2
    config: RunConfig,
) -> InterfaceContext:
    """
    target_class from Phase 2 localization.compartment:
      Extracellular → "extracellular"
      Membrane      → "membrane"
      Intracellular with pLDDT < 70 → "disordered"
      Intracellular with pLDDT ≥ 70 → "intracellular"

    design_strategy assignment:
      "extracellular" → "antibody_epitope"
      "membrane"      → "antibody_epitope" (target ECD)
      "disordered"    → "stapled_peptide"    (helix mimetic for IDP binding)
      "intracellular" → "cyclic_peptide"     (proteolytic resistance + cell penetration)
      Exception: is_master_regulator=True → "helical_mimetic" (TF interface)

    binder_length_range:
      cyclic_peptide:   (8, 20)
      stapled_peptide:  (14, 21)
      helical_mimetic:  (14, 21)
      antibody_epitope: (12, 30)

    hotspots = union of:
      - AlphaMissense am_hotspot_residues (Phase 2 variants)
      - fpocket pocket residues with high contact_frequency (Phase 2 pockets[0].residues[:5])
    
    LLM gate 6.1_hotspot_selection to curate and rank hotspots.
    """
```

**LLM gate `6.1_hotspot_selection`:**
```
When: always (hotspot selection is a design-critical decision)
Prompt: "Target: {symbol}. Design strategy: {design_strategy}.
         Candidate hotspot residues from AlphaMissense: {am_hotspots}.
         Pocket contact residues: {pocket_residues}.
         Known PPI interface residues from literature (if any): {ppi_info}.
         Select the 3-5 most important hotspot residues for binder design.
         For {design_strategy}: {strategy_rationale}."
Output schema: {
  "hotspots": [47, 89, 112],
  "reasoning": "...",
  "design_strategy": "cyclic_peptide"
}
Fallback: top 5 by AlphaMissense score
```

---

## 4. Step 6.2 — Sequence Generation: Four-Tier Ladder (`peptide_gen.py`)

### Generation priority order

```
Tier 1: BoltzGen (Neurosnap) → ProteinMPNN local
Tier 2: RFdiffusion NIM      → ProteinMPNN local
Tier 3: ProteinMPNN directly on target PDB (no backbone generation)
Tier 4: LLM-assisted generation (last resort, always available)
```

The pipeline tries each tier in order and uses the first that returns non-empty sequences.

### Tier 1: BoltzGen → ProteinMPNN (`neurosnap_boltzgen.py`)

```python
def run_boltzgen(
    interface_ctx: InterfaceContext,
    n_designs: int = 50,
) -> List[str]:
    """
    Requires NEUROSNAP_API_KEY.
    
    POST https://api.neurosnap.ai/v1/boltzgen
    Headers: {"Authorization": "Bearer {NEUROSNAP_API_KEY}"}
    Body: {
      "target_pdb": base64(pdb_bytes),
      "hotspot_residues": interface_ctx.hotspots,
      "binder_length": interface_ctx.binder_length_range,
      "n_samples": n_designs
    }
    
    Returns list of PDB-format strings (binder-target complexes).
    Each PDB: chain A = target, chain B = designed binder.
    Extract chain B sequence from PDB SEQRES records.
    
    Then run ProteinMPNN on each backbone (Tier 1b):
      _run_mpnn_on_sequences(backbones, interface_ctx)
      → 8 sequence variants per backbone
    """
```

### Tier 2: RFdiffusion NIM (`nim_rfdiffusion.py`)

```python
def run_rfdiffusion_nim(
    interface_ctx: InterfaceContext,
    n_backbones: int = 50,
) -> List[str]:
    """
    Requires NIM_API_KEY.
    
    POST to NVIDIA NIM RFdiffusion binder hallucination endpoint.
    Input: target PDB + hotspot residues as "A47,A89,A112" format
           + binder_length_range + n_designs
    
    Returns list of backbone PDB strings.
    Then run ProteinMPNN sequence design on each backbone.
    
    Note: RFdiffusion model requires ~24 GB VRAM → NIM provides hosted inference.
    Local RFdiffusion NOT attempted (exceeds RTX 3050 VRAM).
    """
```

### Tier 3: ProteinMPNN on target PDB (`proteinmpnn_runner.py`)

```python
def is_available() -> bool:
    """Check if tools/ProteinMPNN/protein_mpnn_run.py exists and torch is importable."""

def design_from_pdb_url(
    pdb_url: str,           # Supabase Storage path, downloaded to temp
    n_sequences: int = 20,
    sampling_temp: float = 0.1,
) -> List[str]:
    """
    Downloads PDB from Supabase Storage to /tmp.
    subprocess: python tools/ProteinMPNN/protein_mpnn_run.py
        --pdb_path {pdb_path}
        --num_seq_per_target {n_sequences}
        --sampling_temp {sampling_temp}
        --out_folder {output_dir}
        --suppress_print 1
    
    Parses FASTA output → list of AA sequences.
    
    Scientific note: At T=0.1, designs sequences compatible with target backbone.
    Produces competitive peptide inhibitors / interface-mimicking peptides.
    """
```

### Tier 4: LLM-Assisted Generation

```python
def generate_with_llm(
    symbol: str,
    interface_ctx: InterfaceContext,
    provider,
    n_sequences: int = 20,
    known_sequences: Optional[List[str]] = None,
) -> List[str]:
    """
    Strategy-specific prompt templates:
      "antibody_epitope": linear 12-20 aa, hydrophilic, ≥1 charged residue
      "cyclic_peptide":   8-16 aa, include Pro/Gly for turn, logP 0-2
      "helical_mimetic":  14-21 aa, i,i+4 heptad repeat, amphipathic
      "stapled_peptide":  14-21 aa, Cys at i,i+4 for stapling
    
    Also queries ChEMBL local for known peptide-like compounds (MW 200-2000,
    pChEMBL ≥ 6, alogP < 3) as reference sequences.
    
    Validation of LLM output:
      - Valid AA single-letter codes only (ACDEFGHIKLMNPQRSTVWY)
      - Length within binder_length_range
      - Distinct from each other (Hamming distance ≥ 3)
    
    Returns: valid sequences extracted from LLM JSON response.
    Note: This is Tier 4 (fallback only). Primary method is BoltzGen/RFdiffusion.
    """
```

---

## 5. Step 6.3 — Refolding Validation

```python
@dataclass
class RefoldResult:
    sequence: str
    iptm: float              # interface predicted TM-score
    pae_interface: float     # mean PAE at interface (Å)
    binder_plddt: float      # mean pLDDT of binder chain
    passes_gate: bool        # iptm >= 0.7 AND pae_interface <= 10 AND binder_plddt >= 80

def validate_by_refolding(
    sequence: str,
    target_pdb: str,
    target_symbol: str,
    config: RunConfig,
) -> RefoldResult:
    """
    Routing:
      1. AlphaFold2 NIM with initial_guess (if NIM_API_KEY):
         POST sequence + target FASTA → multimer complex
         Parse pTM, ipTM, PAE matrix from result JSON
      2. Boltz-2 Neurosnap (if NEUROSNAP_API_KEY AND AF2-NIM fails):
         Handles harder targets; returns similar confidence metrics
      3. AF3 Server (cofactor complexes only — if AF3 session available)
    
    ipTM threshold: >= 0.7 (Evans et al. 2022 precision-recall optimum)
    pAE_interface = mean PAE over inter-chain residue pairs within 8Å
    binder_pLDDT threshold: >= 80
    
    Borderline zone ipTM [0.65, 0.75): → LLM gate 6.3_borderline_triage
    """
```

**LLM gate `6.3_borderline_triage`:**
```
When: ipTM in [0.65, 0.75) (borderline zone)
Prompt: "Designed binder for {symbol}. Sequence: {sequence}.
         ipTM: {iptm:.3f}, pAE_interface: {pae:.1f}, binder_pLDDT: {pldt:.1f}.
         Number of interface contacts: {n_contacts}.
         Known experimental evidence for short binders at this interface: {lit_hint}.
         Should this borderline design be promoted for downstream evaluation?
         Consider: concentrated interface uncertainty vs global uncertainty,
                   target flexibility, known binding mode."
Output schema: {"promoted": bool, "reasoning": "...", "confidence": 0.0-1.0}
Fallback: promote if ipTM >= 0.68 (softer threshold)
```

---

## 6. Step 6.4 — Peptide-Specific Processing

```python
def apply_cyclic_flag(sequence: str, design_strategy: str) -> str:
    """
    For cyclic_peptide and stapled_peptide strategies:
      Mark sequence as cyclic in output metadata (N→C ligation flag).
      N-end rule does NOT apply to cyclic peptides → nend_stability_score = 1.0
    """
```

---

## 7. Step 6.5 — Developability (`developability.py`)

```python
@dataclass
class DevelopabilityResult:
    aggregation_flag: bool       # KD window > 1.8 OR Aggrescan3D flag
    solubility_score: float      # 0-1, NetSolP-1.0 proxy
    immunogenicity_score: float  # 0-1 (lower = less immunogenic)
    mhc_strong_binders: int      # count of strong MHC-I binders (rank ≤ 0.5%)
    nend_stable: bool            # N-end rule stability
    dev_score: float             # composite developability score
    passes_gate: bool

def check_developability(
    sequence: str,
    design_strategy: str,
    config: RunConfig,
) -> DevelopabilityResult:
    """
    1. Aggregation (local Kyte-Doolittle):
       6-residue sliding window; flag if any window mean KD > 1.8
       
       Aggrescan3D via Neurosnap (if NEUROSNAP_API_KEY and folded structure available):
         POST folded complex PDB → per-residue aggregation score
         More accurate than sequence-only KD (AUC 0.81 vs 0.68)
    
    2. Solubility heuristic (NetSolP proxy):
       net_charge = sum(+1 for K/R, -1 for D/E) at pH 7.4
       hydrophobicity = mean KD across sequence
       passes = (net_charge >= -2) AND (hydrophobicity < 1.5)
       solubility_score = 0.8 if passes else 0.3
       
       NetSolP-1.0 via Neurosnap API (if available): transformer-predicted solubility
    
    3. Immunogenicity — NetMHCpan 4.2 local:
       For each 9-mer window:
         Run netMHCpan -a {alleles} -p {9mer} -s
         alleles: HLA-A*02:01, HLA-A*01:01, HLA-A*03:01, HLA-B*07:02, HLA-B*44:02
         Count strong binders: rank ≤ 0.5%
       mhc_strong_binders = total count
       Threshold: ≤ 5 for non-chronic, ≤ 3 for chronic indication
    
    4. N-end rule stability:
       For linear peptides: check first residue stability
         Stable: M, A, S, V, T, G, C, P (after Met cleavage rules)
         Unstable: N, Q, D, E → arginylation → proteasomal degradation
         nend_stable = first_residue not in {"N", "Q", "D", "E"}
       For cyclic peptides: nend_stable = True always (no free N-terminus)
    
    Composite dev_score:
      dev_score = (
        0.3 * (not aggregation_flag) +
        0.3 * solubility_score +
        0.3 * max(0, 1.0 - mhc_strong_binders/10.0) +
        0.1 * nend_stable
      )
    
    passes_gate:
      not aggregation_flag
      AND solubility_score > 0.5
      AND mhc_strong_binders <= (3 if indication_type=="chronic" else 5)
    """
```

**LLM gate `6.5_immunogenicity_report`:**
```
When: mhc_strong_binders > 3 OR indication_type == "chronic"
Prompt: "Designed binder sequence: {sequence}.
         NetMHCpan results: {mhc_strong_binders} strong MHC-I binders.
         Indication type: {indication_type}, disease: {disease_label}.
         Administration route expected: systemic.
         Is this immunogenicity profile acceptable?
         What de-immunization approach would you recommend if not?"
Output schema: {
  "acceptable": bool,
  "risk_level": "low" | "moderate" | "high",
  "recommendations": ["..."],
  "deimmunization_priority": "none" | "optional" | "required"
}
Fallback: acceptable = (mhc_strong_binders <= 5), risk_level based on count
```

---

## 8. Combined Pre-Phase-8 Score

```python
def compute_combined_pre8_biologic(
    refold: RefoldResult,
    dev: DevelopabilityResult,
    config: RunConfig,
) -> float:
    """
    combined_pre8 = (
        0.40 * refold.iptm +
        0.30 * dev.dev_score +
        0.20 * (refold.binder_plddt / 100.0) +
        0.10 * (1.0 - refold.pae_interface / 20.0)  # lower PAE = better
    )
    """
```

---

## 9. Output JSON Contract

```json
{
  "biologic": {
    "TGFB1": [
      {
        "id": "PEP_001",
        "sequence": "CLDPIYWARYADWLFTTPL",
        "type": "cyclic_peptide",
        "length": 19,
        "source_tier": 1,
        "iptm": 0.82,
        "pae_interface": 7.3,
        "binder_plddt": 84,
        "developability": {
          "aggregation": false,
          "solubility_score": 0.71,
          "mhc_strong_binders": 3,
          "nend_stable": true
        },
        "combined_pre8": 0.78,
        "design_strategy": "cyclic_peptide",
        "hotspots_used": [47, 89, 112]
      }
    ]
  },
  "n_targets": 6,
  "n_candidates_total": 28,
  "wall_time_s": 3600
}
```

---

## 10. DB Writes

```
phase_results: phase=6, running → completed
candidates: one row per (target, sequence) passing refold + developability gates
            kind="biologic" or "peptide"
            target_id = symbol
            sequence = AA sequence
            combined_score = combined_pre8
            subscores = {iptm, pae_interface, binder_plddt, dev_score, mhc_binders}
            artifact_paths = [complex PDB path in Storage]
decisions: gate="6.1_hotspot_selection", gate="6.3_borderline_triage",
           gate="6.5_immunogenicity_report"
compute_log: step="boltzgen" service="neurosnap"
             step="rfdiffusion_nim" service="NIM"
             step="proteinmpnn" service="local"
             step="af2_refold" service="NIM"
```

---

## 11. Failure / Recovery

| Failure | Recovery |
|---|---|
| All ipTM < 0.7 | Widen RFdiffusion sampling (increase n_backbones); shift hotspots; if persistent → poor PPI candidate, switch to peptide route |
| BoltzGen API unavailable | Fall to Tier 2 (RFdiffusion NIM) |
| RFdiffusion NIM unavailable | Fall to Tier 3 (ProteinMPNN on target) |
| ProteinMPNN not installed | Fall to Tier 4 (LLM generation) |
| Aggregation flag on all | Introduce surface charge patches; re-MPNN with charged residue bias |
| All immunogenic (chronic indication) | Disqualify entire batch; flag de-immunization needed |
| Neurosnap credits exhausted | RFdiffusion NIM + AF2 NIM; warn on budget |

---

## 12. Key Scientific Notes

- **Tier 4 (LLM) is last resort only** — it has no structural knowledge and produces sequences that may fold incorrectly. Refolding validation (Step 6.3) will catch these. It exists purely as a graceful degradation path.
- **Cyclic peptides**: N→C cyclisation removes free N-terminus → N-end rule inapplicable + proteolytic stability. Intracellular targets always get cyclic design strategy.
- **ipTM ≥ 0.70 threshold**: Evans et al. 2022 calibration — precision=0.86, recall=0.78. ipTM ≥ 0.80 would miss true binders (recall=0.62).
- **NetMHCpan 5-allele panel**: HLA-A\*02:01, A\*01:01, A\*03:01, B\*07:02, B\*44:02 covers ~80% of clinically observed T-cell-mediated immunogenicity responses.
