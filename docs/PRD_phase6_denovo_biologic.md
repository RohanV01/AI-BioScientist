# PRD — Phase 6: De Novo Biologic / Peptide Design

**Maps to:** Human Pipeline.md §PHASE 6
**Celery queue:** `hosted` (BoltzGen/RFdiffusion/AF2 NIM/Neurosnap), `gpu` (ProteinMPNN local), `cpu` (NetMHCpan), `llm`
**Depends on:** Phase 3 routing (`P6_biologic` branch)

---

## Goal

For AB/peptide-routed targets (or SM targets with undruggable pockets), **design protein/peptide binders** to the target interface, validate by refolding, and pass developability (aggregation, solubility, immunogenicity, humanization). Output top binders per target. Heavy reliance on hosted compute — **BindCraft is OUT on 6 GB** (routed to BoltzGen / RFdiffusion NIM).

Runs when `intent_mode ∈ {explore, de_novo}`.

---

## Inputs Required From You

### Software (local)
- conda env `rxdis`: ProteinMPNN (clone; local OK for <150 aa), NetMHCpan 4.1 (free academic install), TANGO CLI (aggregation)
- LM Studio server live

### Databases / APIs
- No large local DB. Human germline IGHV reference (for humanization).

### Accounts / APIs (heavy hosted use)
- Neurosnap (BoltzGen primary, Boltz-2, Aggrescan3D, NetSolP, ColabDock, ImmuneBuilder) — `NEUROSNAP_API_KEY`
- NVIDIA NIM (RFdiffusion fallback ≥12 GB hosted, AlphaFold2 refolding, ProteinMPNN for larger) — `NIM_API_KEY`
- AlphaFold Server (AF3 for ligand/cofactor complexes) — session/key
- SAbPred OPIG webserver (browser, humanization), CamSol (browser)
- (optional, paid) RunPod A100 for BindCraft-quality

### From config
- `seed_targets` interface hints if provided
- `indication_type` (chronic non-cancer → immunogenicity is disqualifying)

---

## Process Steps (per target)

### 6.1 Backbone generation (hosted-only)
- **Primary: BoltzGen via Neurosnap** — target + binder length range (30–120 aa mini-binders; 8–30 peptides) + cyclic flag + hotspots. 50–200 backbones.
- Fallback: RFdiffusion NIM (12 GB hosted).
- BindCraft only if paying Neurosnap / renting A100.

### 6.2 Sequence design
- ProteinMPNN local (binders <150 aa) or NIM for larger. ~8 sequences/backbone.

### 6.3 Refolding validation
- AlphaFold2 NIM with `initial_guess` for binder-target complex; Boltz-2 (Neurosnap) for harder; AF3 Server for cofactor complexes.
- Gate: ipTM >0.7 AND pAE_interface <10 Å AND binder pLDDT >80.

### 6.4 Peptide-specific (8–30 aa)
- ProtFlow (if exposed on Neurosnap, else BoltzGen substitute); HelixGAN (helical); AfCycDesign/cyclic mode.
- Cyclize if intracellular target (proteolytic stability).

### 6.5 Developability
- Aggregation: CamSol / Aggrescan3D (Neurosnap) / TANGO local.
- Solubility: NetSolP-1.0 (Neurosnap).
- Immunogenicity: NetMHCpan 4.1 local (MHC-I/II; 500 nM strong threshold).
- Humanization: SAbPred Humanness; IGHV germline identity.
- Gate: no aggregation hotspot >median, solubility >0.6, <5 strong MHC binders.

---

## Local-LLM Decision Points

| Gate | Decision | Output schema |
|---|---|---|
| `6.1_hotspot_selection` | select 3–5 hotspot residues from mutations + PPI interface + AM residues + pocket | `{hotspots[],reasoning,design_strategy}` |
| `6.3_borderline_triage` | rank borderline ipTM (0.65–0.75) designs by contacts/pAE; promote 1–2 | `{promoted[],reasoning}` |
| `6.5_immunogenicity_report` | acceptability given indication + route; de-immunization need | `{acceptable,risk_level,recommendations[],deimmunization_priority}` |

---

## I/O Contract

**Input:** Phase 3 routing + Phase 2 structure (target PDB, interface).

**Output (`phase_results.output_json` for phase 6):**
```json
{"biologic":{
  "TGFB1":[
    {"id":"PEP_001","sequence":"CXXXXXXC","type":"cyclic_peptide","length":16,
     "iptm":0.82,"pae_interface":7.3,"binder_plddt":84,
     "developability":{"aggregation":"pass","solubility":0.71,"mhc_strong_binders":3},
     "combined_pre8":0.78}
  ]
}}
```
Writes `candidates` rows with `kind='biologic'` or `'peptide'`, sequence; complex PDB → Storage.

---

## Success Criteria

1. ipTM >0.7 on a benchmark like PD-L1.
2. BindCraft is never attempted locally on 6 GB (routed out).
3. Cyclic peptides chosen for intracellular targets.
4. Chronic non-cancer indication → immunogenic designs flagged disqualifying.
5. Developability gate enforced (aggregation/solubility/MHC).

---

## Failure / Recovery

| Failure | Recovery |
|---|---|
| All ipTM <0.7 | widen RFdiffusion sampling / shift hotspots; if persistent → poor PPI candidate, switch to peptide route |
| Aggregation flag on all | introduce surface charge, break hydrophobic patch, re-MPNN |
| Immunogenic for all (chronic) | disqualify; flag de-immunization (out of scope) |
| BindCraft GPU OOM | switch to BoltzGen (Neurosnap) or RFdiffusion NIM |
| Neurosnap credits exhausted | RFdiffusion NIM + AF2 NIM path; warn on budget |
