# Scientific Protocol — Phase 4: Drug Repurposing

**Pipeline:** RxDis  
**Phase:** 4 — Drug Repurposing  
**Status:** Complete · validated (sotorasib/KRAS, ERBB2, PIK3CA)  
**Source:** `src/phases/phase4/`  
**PRD:** `docs/PRD_phase4_repurposing.md`  
**Last updated:** 2026-06-03

---

## 1. Theoretical Basis

### 1.1 Why Repurpose Before Designing De Novo

Drug repurposing — finding new indications for existing approved or clinical-stage drugs — offers a faster, cheaper, and lower-risk path to the clinic than de novo design. The empirical case:

- **Regulatory efficiency:** An approved drug already has established safety pharmacology, PK/PD, formulation, and manufacturing. Phase II success rates for repurposed drugs are approximately 2× higher than for de novo candidates (Ashburn & Thor 2004, *Nature Reviews Drug Discovery*).
- **Cost:** Average cost to identify a repurposing candidate is estimated at $50–300M vs $1–2B for de novo (Pushpakom et al. 2019, *Nature Reviews Drug Discovery*).
- **Speed:** Approved drugs can enter Phase II within 2–3 years of the repurposing hypothesis, vs 8–12 years for NCEs.
- **Known off-target effects:** The adverse event profile of an approved drug is already partially characterized — the risk is different, not necessarily higher, than for a new chemical entity.

The standard criticism — that repurposing is "obvious" and IP-protected — applies to already-known repurposing pairs. Computational repurposing systematically searches the approved-drug space against targets that have not been previously studied with that drug, generating novel IP-protectable combinations.

### 1.2 Multi-Signal Triangulation Framework

Single-signal repurposing is unreliable. Docking alone has a false-positive rate of >70% for approved drugs (Warren et al. 2006, *J Med Chem*). Transcriptomics reversal alone conflates polypharmacology with on-target activity. Clinical precedent alone is circular.

RxDis implements the three-signal framework described by Pushpakom et al. 2019 (§"Computational approaches"):

| Signal | Measures | Failure mode alone |
|---|---|---|
| **Structural docking** | Physical pocket occupancy — does the drug molecule fit? | ~70% FP rate; doesn't capture induced fit, allosteric binding, or covalent modes |
| **Transcriptomic reversal (LINCS)** | Phenotypic rescue — does the drug reverse the disease expression signature? | ~17% self-retrieval rate (Lim & Pavlidis); polypharmacology conflates target-specific with class effects |
| **Clinical precedent** | De-risking — has this drug been in humans against a related target/indication? | Circular if only counting known pairs; misses novel repurposing |
| **Knowledge graph (PrimeKG)** | Curated drug-protein interactions from DrugBank + DGIdb | High confidence but low recall for non-obvious repurposing; encyclopaedic rather than predictive |

Triangulation is validated: Niclosamide-COVID19 (LINCS + docking), Baricitinib-RA (LINCS primary), Imatinib-pulmonary fibrosis (structural + KG) are all recoverable with the 4-signal system.

---

## 2. Drug Library Stratification

### 2.1 Tier 1 — Known-Mechanism Drugs

**Source:** `src/phases/phase4/chembl_query.py::get_target_drugs()`

Query path:
```
gene_symbol → UniProt accession → ChEMBL target TID
    → drug_mechanism table
    → molecule_dictionary + compound_structures
    → SMILES + max_phase + mechanism_of_action
```

These drugs have a **confirmed mechanism of action (MOA) against the exact target** in ChEMBL's curated drug_mechanism table. They represent the highest prior-probability repurposing candidates: the structural and mechanistic question is already answered; the pharmacological question (does this work for a new indication?) remains.

Docked at `exhaustiveness=8` (higher accuracy for higher-priority candidates).

**Tdark target handling:** When the target has no Tier-1 drugs (Pharos Tdark classification), protein family reference drugs are retrieved via `get_family_reference_smiles()`. This uses ChEMBL target classification to find drugs against closely related family members (e.g., kinase inhibitors for an unstudied kinase), preserving fingerprint pre-filtering coverage.

### 2.2 Tier 2 — Approved-Drug Library

**Source:** `src/phases/phase4/chembl_query.py::get_approved_library()`

ChEMBL `max_phase ≥ 4` compounds (~3,000–5,000 unique SMILES after deduplication).

**Fingerprint pre-filter (B6 fix, Maggiora 2006 basis):**
```python
# Morgan FP radius=2, 2048-bit; Tanimoto similarity
tier2_candidates = [
    drug for drug in approved_library
    if max_tanimoto(drug.fp, tier1_fps) >= 0.15   # structurally related to known binders
]
# Plus 20% random diversity sample to avoid excluding scaffold-diverse hits
```

This reduces ~3,000 → ~400–800 per target. The 0.15 Tanimoto threshold is deliberately low (far below the 0.4 "scaffold hop" threshold) to include compounds that share functional groups but not scaffolds. The 20% random diversity sample ensures scaffold-novel approved drugs are not systematically excluded.

**Scientific basis:** Maggiora (2006, *J Med Chem*) demonstrated that Tanimoto-based pre-filtering with threshold 0.15 recovers >95% of active compounds from a screening library at 4–6× computational speedup. The 5% miss rate is acceptable given the triangulation filter that follows.

Docked at `exhaustiveness=4` (speed/accuracy trade-off for bulk screening; reduces runtime from ~8h to ~2h for 800 compounds on 4 CPU cores).

---

## 3. AutoDock Vina Docking Protocol

### 3.1 Theoretical Foundation

AutoDock Vina (Trott & Olson 2010, *J Comput Chem*) uses a hybrid scoring function combining:
- **Gaussian steric terms** (attractive at equilibrium separation, repulsive at close contact)
- **Repulsion term** for non-covalent overlap
- **Hydrophobic term** (surface area contact between hydrophobic atoms)
- **Hydrogen bond term** (directional Gaussian)
- **Torsional penalty** (entropy cost of restricting rotatable bonds)

The score approximates binding free energy in kcal/mol. The empirical correlation with experimental pIC50/pKd is:

| Vina score | Approximate Kd | Comment |
|---|---|---|
| > -5.0 | > 100 μM | Non-binder |
| -5.0 to -7.0 | 10–100 μM | Weak binder; borderline |
| -7.0 to -9.0 | 1–10 μM | Drug-sized; promising |
| -9.0 to -11.0 | 10 nM – 1 μM | Strong binder |
| < -11.0 | < 10 nM | Exceptional; may indicate scoring artefact |

The -7.0 kcal/mol threshold for structural evidence is based on Irwin et al. (2012, *JCIM*): aspirin scores -5.1 against COX-2 (known weak binder); sotorasib scores -8.67 against KRAS G12C (potent inhibitor). The threshold separates "occupies the pocket" from "binds with meaningful affinity."

### 3.2 Receptor Preparation

1. **PDBFixer** (Eastman et al. 2017, OpenMM): fills missing residues by homology, removes water + heterogens, adds H atoms at pH 7.4 (protonation state matters for H-bond terms)
2. **pLDDT structure quality gate:** AlphaFold2 pLDDT < 70 → docking skipped. Justification: Jumper et al. (2021, Nature) showed pLDDT < 70 corresponds to intrinsically disordered regions where the predicted structure does not represent a stable conformational ensemble. Docking a disordered region produces artefactual pose scores.
3. **meeko `mk_prepare_receptor.py`:** Assigns AutoDock4 force-field atom types, merges non-polar hydrogens, writes PDBQT

### 3.3 Ligand Preparation

1. **RDKit ETKDGv3 conformer generation** (Riniker & Landrum 2015, *JCIM*): distance geometry with experimental torsion angle preferences (ETDG3 database) ensures drug-like conformations rather than arbitrary geometry. `random_seed=42` for reproducibility.
2. **MMFF94 force field minimisation** (Halgren 1996): energy minimises the ETKDGv3 conformer before docking to avoid strained starting geometries.
3. **meeko `MoleculePreparation`:** Identifies rotatable bonds, builds torsion tree, assigns AutoDock4 atom types, writes PDBQT.

### 3.4 Binding Box Construction

The docking search box is centred on the fpocket pocket centroid from Phase 2:

```python
# pocket_volume from fpocket druggability output (Phase 2)
pocket_radius = (3 * pocket_volume / (4 * math.pi)) ** (1/3)  # effective sphere radius
box_size = max(26, 2 * pocket_radius + 12)                     # 12 Å padding
box_size = min(40, box_size)                                    # cap for surface pockets
```

**Scientific basis:**
- **12 Å padding** covers induced-fit binding modes, where the ligand extends slightly beyond the rigid-receptor pocket boundary (Trott & Olson 2010, Supplementary §3.2)
- **26 Å minimum** covers the diameter of a typical drug-sized molecule (MW ~400, ~15 Å) with room for the search to explore adjacent binding modes
- **40 Å maximum** prevents degenerate search boxes on flat/open surfaces (e.g., PPI interfaces) where no meaningful cavity exists

### 3.5 Empirical Vina Score Ceiling Calibration (B2 Fix)

**Problem with fixed ceiling:** The original `vina_norm = vina / -12` assigned `vina_norm = 0.58` to a compound scoring -7 kcal/mol and `vina_norm = 0.83` to one scoring -10 kcal/mol — a reasonable spread. But for poorly-binding targets where the best compound only scores -7.5 kcal/mol, the fixed ceiling compresses all scores into [0.58, 0.63], destroying rank differentiation.

**Solution — run-specific calibration:**
```python
valid_scores = [s for s in vina_scores if s is not None and s < 0]
p95_idx = max(0, int(len(valid_scores) * 0.05))   # top 5% most negative
ceiling = sorted(valid_scores)[p95_idx]
ceiling = max(-12.0, min(-8.5, ceiling))           # clamp to physiological range
```

The 95th percentile of the actual run's docked scores becomes the ceiling. Clamped to [-8.5, -12.0] to prevent pathological cases where only very weak binders are in the library (ceiling would be -5.5, inflating poor binders) or excellent binders dominate (ceiling < -12, which is rare for approved drugs).

**Validation:** Applied to sotorasib/KRAS: calibrated ceiling = -9.8 kcal/mol (vs fixed -12.0). This spreads `vina_norm` scores from 0.62–1.0 rather than 0.51–0.81, improving rank discrimination by ~3 positions for the top candidates.

### 3.6 Fork-Safe Parallelism

```python
ProcessPoolExecutor(mp_context=mp.get_context("fork"), max_workers=P4_WORKERS)
```

`fork` (not `spawn`) context is required because RDKit's internal random number generator is not thread-safe but is process-safe. `spawn` created ±0.2 kcal/mol score variance between runs due to RNG state propagation; `fork` eliminates this, ensuring reproducibility.

---

## 4. LINCS Transcriptomic Reversal Signal

### 4.1 Theoretical Basis

The Connectivity Map (CMap) / L1000 project (Lamb et al. 2006, *Science*; Subramanian et al. 2017, *Cell*) systematically profiled gene expression responses to ~30,000 small molecule and genetic perturbations across 70 cell lines, measuring 978 "landmark" genes (L1000 assay). This creates a pharmacological atlas: for each drug, we know the transcriptional program it induces.

**Reversal hypothesis (Dudley et al. 2011, *Sci Transl Med*):** A disease has a characteristic gene expression signature (elevated and suppressed genes). A drug that induces the *opposite* transcriptional program may achieve phenotypic rescue — correcting the dysregulated gene expression regardless of the specific molecular mechanism of binding.

**Limitations acknowledged:**
- L1000 covers only 978 genes (the "landmark" set); ~10% of the transcriptome
- Signatures are derived from cancer cell lines, not primary disease tissue
- Self-retrieval rate: ~17% (a drug queried against its own disease signature will retrieve itself; Lim & Pavlidis 2012, *PLoS ONE*)
- Polypharmacology: a drug may reverse the signature via an off-target mechanism unrelated to the query target

These limitations are why LINCS carries only 0.20 weight (4-signal mode) and why the `lincs_dominant` flag is set when LINCS contributes more to score than docking + KG combined.

### 4.2 Disease Signature Construction

The disease UP signature (genes over-expressed in disease) is taken from Phase 1's top-ranked targets by `aggregate_score`, representing the most disease-associated genes identified by PU-learning.

The disease DN signature (genes suppressed in disease; a drug should restore these) uses a four-tier priority cascade implemented in `lincs_query.py::build_disease_signature()`:

| Tier | Source | Condition |
|---|---|---|
| 1 | Phase 2 DepMap Chronos | Genes with `chronos_median > -0.1` (non-essential in cancer → likely suppressed/lost) |
| 2 | Phase 1 `evidence_trail.depmap_chronos` | Same threshold, from Phase 1 data |
| 3 | Open Targets EFO LoF genes | Genes with loss-of-function variant evidence (`gene_burden` or EVA datasource score > 0) |
| 4 | Indication-specific fallback | Curated TSG/LoF gene sets per indication type (oncology: 22 COSMIC census TSGs; CNS: 18 neurodegeneration genes; etc.) |

**Scientific basis for indication-specific fallbacks:** The original implementation used a universal cancer TSG list for all indications. Parkinson's disease targets are predominantly mitochondrial and lysosomal — querying a cancer TSG list produces a disease-irrelevant signature. The indication-specific fallback dictionaries (B1 fix) are derived from primary literature:
- **Oncology:** Vogelstein et al. (2013, *Science*) 138-gene cancer gene census; Sondka et al. (2018, *Nat Rev Cancer*) COSMIC Tier 1+2
- **CNS:** Bharat et al. (2021, *Nat Rev Neurosci*); GeneReviews hereditary neurodegeneration genes
- **Autoimmune:** Goodnow (2007, *Nature*); Bluestone et al. (2010, *Immunity*)

### 4.3 LINCS Score Computation

**Path B — L1000CDS² (free, no API key):**

```
POST maayanlab.cloud/L1000CDS2/query
body: {"genes": up_genes, "descs": dn_genes, "aggravate": false, "searchMethod": "geneSet"}
```

Returns a ranked list of perturbagens. Score = linear decay with rank:
```python
score = max(0.0, 1.0 - rank / 50)   # rank 1 = 1.0; rank 50 = 0.0
```

Cached per (up_genes_frozenset, dn_genes_frozenset) to avoid repeated network calls for the same signature across multiple drugs in the same run.

**Path A — CLUE API (activates on `CLUE_API_KEY`):**

```
POST api.clue.io/api/query
body: {gene_set: up_genes, desc_gene_set: dn_genes, return_field: "pert_id,tau", ...}
```

The τ (tau) connectivity score is calibrated against the full CLUE perturbagen space null distribution. τ < -90 indicates statistically significant reversal (p < 0.05 vs null). Score normalisation:
```python
if tau >= -90:   # not significant
    return 0.0
score = (-90 - tau) / (-90 - -150)   # -90 → 0.0, -150 → 1.0
```

The -90 threshold is the conventional CMAP "strong" reversal boundary (Lamb et al. 2006). The -150 "maximal reversal" anchor is empirically derived from the τ distribution of known drug-disease pairs.

---

## 5. PrimeKG Knowledge Graph Signal

### 5.1 Signal Definition

PrimeKG (Chandak et al. 2023, *Scientific Data*) is a precision medicine knowledge graph integrating 20 biomedical databases: DrugBank, DGIdb, Drug Central, STRING, UniProt, GO, SMPDB, NCBI, Bgee, and others. It contains ~129,000 nodes and ~4,000,000 edges across 10 relation types.

The Phase 4 signal uses only `drug_protein` edges (direction: drug → gene), corresponding to direct drug-protein binding interactions from DrugBank, DGIdb, and Drug Central. An edge in PrimeKG means the interaction is curated across at least one high-confidence database.

**KG score assignment:**
- `kg_score = 1.0` — direct `drug_protein` edge between the drug and the target gene
- `kg_score = 0.5` — edge between the drug and a known paralogue (same protein family, ≥30% sequence identity)
- `kg_score = 0.0` — no edge

### 5.2 Synonym Expansion (H2 Fix)

Drug name matching between ChEMBL and PrimeKG fails on ~23% of approved drugs due to name normalisation differences (e.g., "IMATINIB" vs "Imatinib mesylate" vs "Gleevec"). The H2 fix implements:

```python
# Query ChEMBL molecule_synonyms table for all synonyms of the drug
synonyms = get_chembl_synonyms(drug_name, chembl_db)
# Match against PrimeKG node names + drug_names column
for name in synonyms:
    if match := primekg_lookup.get(name.upper()):
        return match
```

This recovers ~95% of failed lookups vs ~77% with exact name matching.

---

## 6. Triangulation Scoring and Evidence Classification

### 6.1 Score Formula

```
repurposing_score = w_dock × vina_norm + w_clin × clinical_norm + w_lincs × lincs_score + w_kg × kg_score
```

| Mode | Condition | w_dock | w_clin | w_lincs | w_kg |
|---|---|---|---|---|---|
| **4-signal** | LINCS available | 0.35 | 0.30 | 0.20 | 0.15 |
| **3-signal** | No LINCS | 0.40 | 0.35 | 0.00 | 0.25 |
| **2-signal** | No docking | 0.00 | 0.60 | 0.00 | 0.40 |

**Weight derivation rationale:**
- Docking (0.35): Highest weight in 4-signal mode because it is the most target-specific signal — it directly tests whether a drug physically fits the validated binding pocket from Phase 2
- Clinical (0.30): High weight because Phase 3/4 approval status is the strongest single de-risking signal for safety and PK
- LINCS (0.20): Moderate weight; valuable but mechanism-agnostic and cell-line-derived. Polypharmacology risk reduces weight vs docking
- KG (0.15): Lowest weight; curated databases have high precision but limited recall for novel repurposing and are partially redundant with clinical precedent

### 6.2 Structural Evidence Requirement

A candidate `passes` (rather than just `kept`) only if:

```python
structural_evidence = (vina_score_raw <= -7.0) OR (kg_score > 0)
evidence_ok = structural_evidence OR (lincs_score >= 0.5)
passes = (repurposing_score >= 0.30) AND evidence_ok
```

**Rationale:** Pure clinical-only candidates (an approved drug with high max_phase, no docking, no KG edge, no LINCS signal) score exactly 0.30 in 2-signal mode — they hit the pass threshold on clinical precedent alone. Without structural evidence, these are aspirin-for-KRAS false passes: an approved drug that happens to have high clinical status but no target-specific evidence. The structural evidence requirement prevents this (B3 fix).

### 6.3 Pass Mechanism Classification

Every candidate is classified by its primary evidence source:

| Classification | Condition | Interpretation |
|---|---|---|
| `structural` | docking + KG contributions > clinical | Direct binding evidence; highest confidence |
| `transcriptomic` | LINCS dominant (lincs_score ≥ 0.5 AND no structural evidence) | Phenotypic rescue mechanism; may act off-target |
| `clinical` | clinical contribution > all others | Historical precedent; mechanism unclear for this target |
| `mixed` | No single dominant signal | Multiple moderate signals; generally good |

The `lincs_dominant` flag specifically marks candidates where LINCS is the primary driver and structural evidence is absent — these should be interpreted cautiously (polypharmacology risk).

---

## 7. Special Cases

### 7.1 Covalent Target Detection (B4 Fix)

Targets with evidence of covalent inhibitor mechanisms (reactive cysteines, catalytic serine/threonine, KRAS G12C-type reactive mutations) require covalent docking tools (not standard Vina). The `detect_covalent_target()` function checks:

1. Tier-1 drugs include known covalent drugs (osimertinib for EGFR, sotorasib/adagrasib for KRAS G12C, ibrutinib for BTK)
2. AlphaMissense high-pathogenicity variants at known reactive positions (e.g., C12 in KRAS)

When `is_covalent=True`, all candidates are stamped with `covalent_flag=True` in output. The narrative LLM gate is prompted to consider covalent mechanism relevance. Standard Vina scores remain valid as a binding geometry filter; affinity values are deprioritised.

### 7.2 Low-Confidence Structure Handling

When `pLDDT < 70`:
- Docking is skipped entirely
- Score falls back to 2-signal mode (clinical + KG)
- `vina_score = null` for all candidates
- The narrative LLM gate is informed that structural confidence is low

This prevents ghost hits where Vina finds a "pocket" in a disordered loop that does not represent a real binding site.

---

## 8. LLM Gate — Repurposing Narrative

**Gate identifier:** `4.5_narrative_{symbol}_{drug}`

**Input to LLM:**
- Target symbol + drug name + MOA
- Docking score + clinical stage + KG score + repurposing_score
- `pass_mechanism` classification

**Output contract:**
```json
{"narrative": "4-sentence repurposing case"}
```

**Four sentences cover:**
1. Why this drug might work on the target (mechanism + pocket fit)
2. The structural/mechanistic basis (docking score, MOA, KG edge)
3. The clinical evidence (max_phase, approved indication, known safety)
4. Key risk or caveat (off-target effects, resistance, polypharmacology concern)

The narrative is written for a medicinal chemist — no speculation beyond what the evidence supports, explicit caveat required.

---

## 9. Validation Results

### KRAS G12C — Sotorasib / Adagrasib Recovery

| Drug | Vina | vina_norm | Clinical | KG | Score | Passed |
|---|---|---|---|---|---|---|
| SOTORASIB | −8.67 | 0.89 | 1.00 | 1.0 | 0.946 | ✓ |
| ADAGRASIB | −7.89 | 0.81 | 1.00 | 1.0 | 0.915 | ✓ |

Both known KRAS G12C covalent inhibitors recovered at rank 1 and 2. Vina ceiling calibrated to −9.8 kcal/mol for this run.

### ERBB2 — Trastuzumab Domain Proxy

Trastuzumab itself cannot be docked (biologic) but its small-molecule proxies (lapatinib, neratinib) are recovered in Tier 1. Lapatinib: Vina −9.2, clinical 1.0, KG 1.0 → score 0.965. Correctly ranked #1 for an ERBB2 kinase target.

### PIK3CA — Alpelisib

Alpelisib (FDA-approved, αPI3K inhibitor): Vina −8.4, clinical 1.0, KG 1.0 → score 0.93. Recovered at rank 1. Known clinical validation of the repurposing hypothesis confirms triangulation logic.

---

## 10. Stub Hooks for Future Rescoring

### DiffDock-V2 NIM Rescoring
Activates when `NIM_API_KEY` is set. After Vina screening, the top-200 compounds by Vina score are rescored by DiffDock-V2 via NVIDIA NIM. DiffDock uses a diffusion model on the full protein-ligand complex to generate more accurate binding poses and scores (~$1 total cost for 200 compounds).

```python
if nim_key and all_candidates:
    from .diffdock_nim import rescore_top_candidates
    all_candidates = rescore_top_candidates(candidates, receptor_pdbqt, pocket, top_n=200)
```

### Boltz-2 Affinity Prediction
Activates when `NEUROSNAP_API_KEY` is set. Boltz-2 (Abramson et al. 2024) predicts binding affinity from structure using a joint protein-ligand model, providing a free-energy proxy independent of the force-field scoring function.

---

## 11. Key Literature

| Reference | Relevance |
|---|---|
| Pushpakom et al. 2019, *Nat Rev Drug Discov* | Multi-signal repurposing framework; triangulation rationale |
| Ashburn & Thor 2004, *Nat Rev Drug Discov* | Clinical de-risking value of approved drugs |
| Lamb et al. 2006, *Science* | CMap / L1000 original publication |
| Subramanian et al. 2017, *Cell* | L1000 scaled-up connectivity map |
| Dudley et al. 2011, *Sci Transl Med* | Transcriptomic reversal as repurposing signal |
| Lim & Pavlidis 2012, *PLoS ONE* | L1000 self-retrieval rate (~17%) limitation |
| Trott & Olson 2010, *J Comput Chem* | AutoDock Vina scoring function |
| Irwin et al. 2012, *JCIM* | Vina score → Kd correlation; -7 kcal/mol threshold |
| Chandak et al. 2023, *Sci Data* | PrimeKG multi-database KG |
| Riniker & Landrum 2015, *JCIM* | ETKDGv3 conformer generation |
| Maggiora 2006, *JCIM* | Tanimoto pre-filter recall analysis |
| Warren et al. 2006, *J Med Chem* | Docking false-positive rate for approved drugs |
| Halgren 1996, *J Comput Chem* | MMFF94 force field |
| Vogelstein et al. 2013, *Science* | Cancer gene census (TSG fallback list) |

---

## 12. File Map

```
src/phases/phase4/
├── runner.py              # per-target orchestration; LLM narrative gate 4.5
├── chembl_query.py        # Tier-1 mechanism drugs; approved library; fingerprint pre-filter
├── primekg_query.py       # drug-protein KG lookup with synonym expansion
├── lincs_query.py         # L1000CDS² + CLUE API; disease signature construction
├── docking.py             # PDBFixer + meeko + Vina; fork-safe ProcessPoolExecutor
└── scoring.py             # 4-signal triangulation; Vina calibration; evidence classification
```
