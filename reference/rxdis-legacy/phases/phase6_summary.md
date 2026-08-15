# Phase 6 — De Novo Biologic / Peptide Design: Summary

**Written:** 2026-06-03  
**Status:** Code complete · Tier 3 (ProteinMPNN) + Tier 4 (LLM) validated · Tier 1+2 activate on API key  
**PRD:** `docs/PRD_phase6_denovo_biologic.md`  
**Source:** `src/phases/phase6/`  
**Bottlenecks log:** `bottlenecks/phase5_phase6.md`  
**Scientific methodology:** `Scientific Protocol/phase6_denovo_biologic.md`

---

## What this phase does

Phase 6 designs novel biologics and peptides de novo against a validated target when Phase 3 routing assigns the `P6_biologic` branch AND `de_novo_enabled=True`. It addresses the subset of targets that are not amenable to small molecules: intracellular disordered regions, protein–protein interfaces, extracellular domains without a small-molecule cavity, and transcription factors where small molecules cannot achieve sufficient selectivity.

The output is up to 10 candidate sequences per target, persisted to the `candidates` table with `kind='biologic'` or `kind='peptide'`, and a `combined_pre8` structural quality score. These proceed to Phase 8 (physics-based pose scoring, MD for biologics) and Phase 9 (summary + report).

---

## Architecture: Interface Analysis → Generation → Refolding Validation → Developability → Score

| Step | Module | What it does |
|---|---|---|
| 6.1 Interface analysis | `interface_analysis.py` | Classify target, identify hotspots, determine design strategy |
| 6.1 LLM gate | `runner.py` | `6.1_hotspot_selection` — LLM confirms or corrects hotspot selection |
| 6.2 Sequence generation | `proteinmpnn_runner.py`, `neurosnap_boltzgen.py`, `nim_rfdiffusion.py`, `peptide_gen.py` | 4-tier generation ladder |
| 6.3 Refolding validation | `runner.py` | Boltz-2 / AF2-Multimer ipTM + pAE_interface |
| 6.3 LLM gate | `runner.py` | `6.3_borderline_triage` — LLM promotes borderline ipTM 0.65–0.75 candidates |
| 6.4 Developability | `developability.py` | Aggregation, solubility, immunogenicity, N-end stability |
| 6.5 LLM gate | `runner.py` | `6.5_immunogenicity_report` — LLM interprets MHC-I epitope landscape |
| 6.6 Scoring | `runner.py` | `combined_pre8` from ipTM + developability |
| 6.7 Persist | `runner.py` | Top-10 per target → `candidates` table |

---

## Interface analysis (step 6.1) — `src/phases/phase6/interface_analysis.py`

Before generating any sequences, Phase 6 characterises the target to determine what kind of biologic should be designed. This step produces four outputs that govern all downstream decisions.

### Target class classification

| Class | Criteria | Design implication |
|---|---|---|
| `extracellular` | OT tractability ≥ 0.8 OR fpocket on extracellular domain | Monoclonal antibody epitope design; full-length protein or Fc-fusion context |
| `intracellular` | fpocket in cytoplasmic region OR known nuclear localisation (GO term) | Cyclic peptide (proteolytic stability critical); PROTAC warhead peptide |
| `disordered` | AFDB median pLDDT < 70 OR IUPred3 > 0.6 for > 50% of sequence | Stapled helical peptide or linear inhibitor of disordered binding interface |
| `membrane` | DeepTMHMM prediction (if installed) OR Uniprot subcellular location = membrane | Loop-targeting antibody; bicyclic peptide for receptor extracellular loop |

### Design strategy mapping

| Target class | `design_strategy` | Rationale |
|---|---|---|
| `extracellular` | `antibody_epitope` | Select discontinuous epitope surface from AFDB structure; ProteinMPNN designs binder sequence |
| `intracellular` | `cyclic_peptide` | N→C head-to-tail cyclisation provides proteolytic resistance; RFdiffusion backbone |
| `disordered` | `stapled_peptide` | Hydrocarbon staple (i, i+4 or i, i+7) pre-organises alpha-helical conformation; designed with helical_mimetic scaffold |
| `membrane` | `helical_mimetic` | Transmembrane helix or loop-targeting approach; avoid membrane burial of charged residues |

### Hotspot identification

Hotspots are defined as residues likely to be critical for binding at the interface. Phase 6 combines two sources:

1. **AlphaMissense pathogenic variants** (from Phase 2 `am_high_path_fraction` data): residues where missense mutations are predicted pathogenic are enriched at functionally important positions — often the binding interface or active site (Cheng et al. 2023, Science).

2. **fpocket residue contact analysis** (from Phase 2 `pockets` data): residues lining the top pocket cavity by druggability score. These are the residues a binder must contact to compete with the ligand binding site.

Hotspot list is passed to the `6.1_hotspot_selection` LLM gate, which is asked to confirm whether the residues make structural sense for the inferred target class. The LLM can add or remove hotspots based on biological knowledge (e.g., noting that a given Gln residue forms a conserved H-bond network critical for the target's conformational change).

### Binder length range

```python
# src/phases/phase6/interface_analysis.py
if design_strategy == "cyclic_peptide":
    binder_length_range = (8, 20)      # Optimal for cell penetration + binding
elif design_strategy == "stapled_peptide":
    binder_length_range = (15, 30)     # Covers 2 heptad repeats minimum
elif design_strategy == "antibody_epitope":
    binder_length_range = (60, 120)    # Nanobody-like (VHH), single-domain
else:
    binder_length_range = (20, 60)     # Default helical binder
```

---

## Generation ladder (step 6.2)

Phase 6 uses a 4-tier generation ladder. Each tier is attempted in order; the pipeline falls through to the next tier if the current tier is unavailable or produces too few sequences (< 3 valid outputs).

### Tier 1 — BoltzGen + ProteinMPNN (requires `NEUROSNAP_API_KEY`)

**BoltzGen** (Neurosnap hosted Boltz-1/2 backbone generation, Abramson et al. 2024): generates binder backbone conformations conditioned on the target structure and hotspot residues. Returns PDB coordinate files of putative binder backbones docked against the target.

**ProteinMPNN** then designs sequences for each generated backbone, optimising for folding energy and binding geometry.

API call via `neurosnap_boltzgen.py`:
```python
response = requests.post(
    "https://api.neurosnap.ai/v1/boltzgen",
    headers={"Authorization": f"Bearer {NEUROSNAP_API_KEY}"},
    json={
        "target_pdb": target_pdb_base64,
        "hotspot_residues": hotspots,
        "binder_length": binder_length_range,
        "n_samples": P6_N_GENERATE  # default 30
    }
)
```

This is the highest-quality path: BoltzGen explicitly models the binder-target complex during backbone generation, ensuring the backbone is physically docked before sequence design begins. ProteinMPNN designs sequences that fold into that backbone with high probability.

### Tier 2 — RFdiffusion NIM + ProteinMPNN (requires `NIM_API_KEY`)

**RFdiffusion** (Watson et al. 2023, Nature) is a diffusion model that generates protein backbone coordinates conditioned on a "hotspot" specification. It produces binder backbones that make van der Waals contact with the specified hotspot residues.

API call via `nim_rfdiffusion.py`:
```python
response = requests.post(
    "https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions/rfdiffusion",
    headers={"Authorization": f"Bearer {NIM_API_KEY}"},
    json={
        "input_pdb": target_pdb_base64,
        "hotspot_residues": hotspot_string,  # e.g. "A45,A67,A89"
        "num_designs": P6_N_GENERATE
    }
)
```

RFdiffusion returns PDB coordinate files. ProteinMPNN then sequences these backbones identically to Tier 1.

**Tier 1 vs Tier 2 scientific difference:** BoltzGen uses a diffusion-based structure predictor (Boltz-2) that jointly models the target and binder from the start, allowing more physically realistic binder geometries. RFdiffusion uses an independently-trained SE(3) diffusion process — slightly less accurate for complex interfaces but faster and more commonly deployed.

### Tier 3 — ProteinMPNN on target PDB (no API key required)

**ProteinMPNN** (Dauparas et al. 2022, Science) is a message-passing graph neural network trained on PDB structures that, given a protein backbone, samples sequences compatible with that backbone. In Tier 3, it is run directly on the **target PDB** — not on a designed binder backbone. This mode designs sequences that fit the **target's own structural context**, which is appropriate for:
- Peptide inhibitors that mimic a native binding partner
- Interface-competitive sequences that occupy the same binding groove as an endogenous ligand

**Installation:** cloned at `tools/ProteinMPNN`:
```bash
git clone https://github.com/dauparas/ProteinMPNN tools/ProteinMPNN
```
Required weight: `tools/ProteinMPNN/vanilla_model_weights/v_48_020.pt` (47 MB, downloaded separately).
Requires: PyTorch CPU 2.12.0 (`.venv/`).

**Subprocess call** (`proteinmpnn_runner.py`):
```bash
python tools/ProteinMPNN/protein_mpnn_run.py \
    --pdb_path {target_pdb} \
    --num_seq_per_target 8 \
    --sampling_temp 0.1 \
    --out_folder {output_dir} \
    --suppress_print 1
```

`sampling_temp=0.1` is low (near-greedy) — this produces sequences highly similar to the native structure (high recovery), which is appropriate for competitive inhibitor design. A higher temperature (0.3–0.5) would produce more diverse sequences but with lower structural compatibility.

Output: sequences written to `{output_dir}/seqs/*.fa` (or `{output_dir}/*.fa` depending on ProteinMPNN version — see bottleneck H3). Each FASTA entry includes log-probability (perplexity) of the sequence given the backbone.

### Tier 4 — LLM-assisted generation (always available)

The LLM is queried with:
- Target symbol, class, design strategy
- Hotspot residues
- Binder length range
- Literature context (PubMed abstract summary for the target + known binder peptides from PDB)

Prompt instructs the LLM to propose 5–10 peptide sequences in FASTA format that would plausibly bind at the identified interface, explaining the structural rationale for each. This tier is always available and serves as the minimum fallback.

**Scientific limitation:** LLM-generated peptide sequences are not validated by structural prediction during generation. They are biologically plausible text but have no guarantee of the sequence-structure relationship without refolding validation (step 6.3).

---

## Refolding validation (step 6.3)

After generation, each candidate sequence undergoes complex structure prediction to assess whether it folds and binds to the target. This is the most scientifically critical gate in Phase 6.

### Validation metrics

| Metric | Definition | Pass threshold | Source |
|---|---|---|---|
| `ipTM` | Interface predicted TM-score: TM-score computed on the interface residues of the predicted complex vs an idealised bound complex | ≥ 0.70 | AlphaFold-Multimer Evans et al. 2022 |
| `pAE_interface` | Mean predicted aligned error (PAE) at the inter-chain interface (Å) | ≤ 10.0 Å | AlphaFold2 PAE output |
| `binder_pLDDT` | Mean per-residue local distance difference test score for the binder chain alone (measures how confidently the binder folds in the complex context) | ≥ 80 | AlphaFold2 |

A candidate **passes** refolding if ALL three criteria are met simultaneously.

The ipTM threshold of 0.70 was established in the AlphaFold-Multimer paper (Evans et al. 2022, bioRxiv): in a benchmark of 4,433 binary protein complexes, ipTM ≥ 0.70 had precision > 0.85 for predicting the complex as "interface TM-score ≥ 0.5" (considered correct complex geometry). For de novo designs, a slightly higher confidence is expected from confirmed binders — the 0.70 threshold is the published precision-recall optimum.

### Refolding backends

1. **Primary:** Boltz-2 via Neurosnap API (`NEUROSNAP_API_KEY`) — returns ipTM, pAE, pLDDT.
2. **Fallback:** AF2-Multimer via NVIDIA NIM (`NIM_API_KEY`).
3. **No API key:** refolding is skipped; `ipTM=None` propagates to scoring; `combined_pre8 = dev_score` only.

### LLM borderline triage gate (6.3_borderline_triage)

Candidates with ipTM in [0.65, 0.75) enter a borderline zone where structural confidence is uncertain. The LLM is provided the full context:
- ipTM value + PAE heatmap description
- binder_pLDDT profile (per-residue — which segments are disordered)
- Target interface hotspot residues
- Sequence composition

The LLM is asked to: (a) assess whether the borderline ipTM is likely a genuine binding failure or a prediction artefact, and (b) recommend whether to promote or discard the candidate. The LLM promotes up to 1–2 borderline candidates per target.

This gate exists because ipTM=0.68 does not categorically mean "wrong" — it can reflect genuine structural uncertainty in disordered regions of the target, multiple binding modes sampled by the predictor, or systematic underconfidence of AF2-Multimer for short peptides.

---

## Developability assessment (step 6.4) — `src/phases/phase6/developability.py`

Biologic candidates are assessed against four developability properties. The `dev_score` is the output:

```python
dev_score = (
    aggregation_score     # 1 - normalised_tango_score
    + solubility_score    # NetSolP proxy
    + immunogenicity_score  # 1 - immunogenicity_burden
    + nend_stability_score  # N-end rule stability
) / 4.0
```

### Aggregation prediction

**Heuristic method (default):** Kyte-Doolittle hydrophobicity scale (Kyte & Doolittle 1982) scanned over 6-amino-acid sliding windows. Windows with mean KD > 1.8 are flagged as aggregation-prone (proxy for TANGO-predicted beta-aggregation-prone segments). Normalized to [0, 1] by `1 - (n_flagged_windows / total_windows)`.

**API method (NEUROSNAP_API_KEY set):** Aggrescan3D via Neurosnap — 3D aggregation score that accounts for burial of hydrophobic residues in the folded structure, not just sequence-level hydrophobicity. Substantially more accurate for folded peptides and mini-proteins.

### Solubility prediction

**Heuristic method (default):** Net charge at pH 7.4 (count of Arg+Lys - Asp+Glu) and mean hydrophobicity (KD scale). The heuristic mirrors the NetSolP-1.0 publication input features (Thumuluri et al. 2021):
```python
net_charge = sum(+1 for aa in seq if aa in 'RK') - sum(+1 for aa in seq if aa in 'DE')
mean_hydrophob = mean(KD_SCALE[aa] for aa in seq)
solubility_score = 1.0 if (net_charge >= -2 and mean_hydrophob < 1.5) else 0.5
```

**API method:** NetSolP-1.0 (Neurosnap) — a transformer model trained on 70,000 solubility measurements. Returns a continuous solubility probability.

### Immunogenicity screening (NetMHCpan 4.2)

NetMHCpan 4.2 (Reynisson et al. 2020, Nucleic Acids Res) predicts MHC class I peptide binding for a panel of clinically relevant HLA supertypes:

| Allele | Supertype | Population frequency |
|---|---|---|
| HLA-A*02:01 | A2 | ~45% in European ancestry |
| HLA-A*01:01 | A1 | ~25% |
| HLA-A*03:01 | A3 | ~22% |
| HLA-B*07:02 | B7 | ~20% |
| HLA-B*44:02 | B44 | ~18% |

The 5-allele panel covers the dominant HLA supertypes accounting for ~80% of immunogenic T-cell responses in clinical antibody trials (De Groot & Martin 2009). 9-mer peptides are predicted (canonical MHC-I presentation length).

**Installation required:** `~/netMHCpan-4.2/` — academic licence, free at DTU Bioinformatics.

**Output:** `immunogenic_epitopes_count` — number of predicted strong binders (rank ≤ 0.5%) across all 9-mer windows of the candidate × all 5 alleles.

```python
immunogenicity_burden = min(1.0, immunogenic_epitopes_count / 5.0)
immunogenicity_score = 1.0 - immunogenicity_burden
```

The LLM gate `6.5_immunogenicity_report` receives the full NetMHCpan table and the candidate sequence, and writes a plain-language report identifying which peptide segments carry immunogenic risk and whether they can be de-immunised (typically by conservative amino acid substitutions away from MHC anchor positions).

### N-end rule stability

The N-end rule (Bachmair et al. 1986, Varshavsky 2019) governs proteasomal degradation based on the N-terminal residue. For a peptide or biologic with an exposed N-terminus:

| N-terminal residue | Stability class | Half-life proxy |
|---|---|---|
| Met, Ala, Thr, Val, Ser, Gly, Cys, Pro | Stabilising | > 20 h |
| Ile, Glu | Intermediate | ~30 min |
| Tyr, Gln, Asn, His | Destabilising (secondary) | ~10 min |
| Asp, Glu, Lys, Arg | Destabilising (primary) | ~2 min |
| Phe, Leu, Trp | Destabilising (type 2) | ~3 min |

```python
# src/phases/phase6/developability.py
NEND_STAB = {'M':1.0,'A':1.0,'T':1.0,'V':1.0,'S':1.0,'G':1.0,'C':1.0,'P':1.0,
             'I':0.6,'E':0.6,'Y':0.4,'Q':0.4,'N':0.4,'H':0.4,
             'D':0.1,'K':0.1,'R':0.1,'F':0.2,'L':0.2,'W':0.2}
nend_stability_score = NEND_STAB.get(seq[0], 0.5)
```

For cyclic peptides (N→C cyclised), the N-end rule does not apply — `nend_stability_score=1.0` is assigned unconditionally because there is no free N-terminus.

---

## Scoring (step 6.6)

### combined_pre8 formula

```python
if iptm is not None:
    iptm_norm = clamp((iptm - 0.60) / 0.40, 0, 1)  # 0.60 → 0.0, 1.00 → 1.0
    combined_pre8 = 0.50 * iptm_norm + 0.50 * dev_score
else:
    # No refolding validation — structural quality unknown
    combined_pre8 = dev_score
```

The 0.50/0.50 ipTM-developability split reflects the equal importance of structural fitness (the molecule must fold and bind) and biologic quality (the molecule must be manufacturable). When ipTM is absent, the score is purely developability-driven — this is scientifically insufficient for structural confidence but is the best available estimate when no API keys are configured.

Pass threshold: `combined_pre8 ≥ 0.40` (slightly relaxed vs Phase 5 SM threshold because biologic candidates are inherently harder to generate and the field size is smaller).

---

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `P6_N_GENERATE` | 30 | Target number of sequences from generation tier |
| `P6_TOP_N` | 10 | Number of top candidates to persist |
| `NEUROSNAP_API_KEY` | — | Activates Tier 1 BoltzGen + Aggrescan3D + NetSolP |
| `NIM_API_KEY` | — | Activates Tier 2 RFdiffusion + AF2-Multimer refolding |

---

## Output contract

```json
{
  "biologic": {
    "SMAD4": [
      {
        "sequence": "MAELYARVQKQLEREEAR",
        "kind": "peptide",
        "design_strategy": "stapled_peptide",
        "combined_pre8": 0.71,
        "iptm": 0.78,
        "pae_interface": 7.4,
        "binder_plddt": 84.2,
        "dev_score": 0.64,
        "aggregation_score": 0.82,
        "solubility_score": 0.71,
        "immunogenicity_score": 0.55,
        "nend_stability_score": 1.0,
        "immunogenic_epitopes": 2,
        "immunogenicity_report": "...",
        "generation_tier": 3,
        "generation_method": "proteinmpnn",
        "hotspots_targeted": ["A45", "A67", "A89"],
        "rank": 1,
        "passed": true
      }
    ]
  },
  "n_generated": 8,
  "n_after_refolding": 5,
  "n_passed_threshold": 3,
  "wall_time_s": 1220.6
}
```

---

## Performance (typical warm run, Tier 3)

```
Step                                      Time       Notes
────────────────────────────────────────────────────────────
6.1  Interface analysis                    ~5s        PDB parsing + GO lookup
6.1  LLM gate (hotspot_selection)          ~8s        1 API call
6.2  ProteinMPNN (Tier 3, 8 sequences)    ~90s        CPU PyTorch, subprocess
6.3  Refolding (no API key)               skipped     ipTM = None
6.4  Developability (8 sequences)         ~15s        Local tools
6.4  NetMHCpan 4.2 (if installed)         ~20s        subprocess, 5 alleles × 8 seqs
6.5  LLM gate (immunogenicity)            ~10s        1 API call
6.6  Scoring + ranking                     ~1s
6.7  DB persist (top-10)                   ~2s
────────────────────────────────────────────────────────────
     TOTAL (Tier 3, no refolding)         ~3 min
     TOTAL (Tier 1, with Boltz-2 refold) ~25 min     API latency dominates
```

---

## File map

```
src/phases/phase6/
├── runner.py               # orchestrator: routing, LLM gates, DB writes, scoring
├── interface_analysis.py   # target class, design strategy, hotspot extraction
├── proteinmpnn_runner.py   # subprocess wrapper for tools/ProteinMPNN
├── neurosnap_boltzgen.py   # Tier 1: BoltzGen API + Aggrescan3D + NetSolP
├── nim_rfdiffusion.py      # Tier 2: RFdiffusion NIM API
├── peptide_gen.py          # Tier 4: LLM-assisted sequence generation
└── developability.py       # aggregation, solubility, immunogenicity, N-end

tools/
├── ProteinMPNN/            # cloned from github.com/dauparas/ProteinMPNN
│   └── vanilla_model_weights/v_48_020.pt

~/netMHCpan-4.2/            # NetMHCpan 4.2 (DTU, academic licence)
```
