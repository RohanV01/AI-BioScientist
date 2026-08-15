# Scientific Methodology: Phase 2 + Phase 3 — Target Validation and Modality Selection

**Document type:** Scientific protocol
**Version:** 1.0 (2026-06-03)
**Status:** Production — validated on 6 targets across breast cancer and pancreatic cancer
**Implementation:** `src/phases/phase2/` · `src/phases/phase3/`
**Operational reference:** `phases/phase2_phase3_summary.md`
**Bottlenecks:** `bottlenecks/phase2_phase3.md`

---

## 1. Scientific Problem Statement

Phase 1 produces a ranked list of candidate drug targets based on biological similarity to confirmed disease-associated genes. The ranking is biologically motivated and disease-specific, but it answers only one question: *does this protein look like something we'd want to drug?* It does not answer whether we actually can.

Phase 2 addresses the three independent questions that determine whether a target is developable:

1. **Is the protein structurally accessible?** A protein must have a cavity or surface that a drug-like molecule can bind with sufficient affinity and selectivity. A disordered, membrane-embedded, or featureless surface is not a directly druggable target regardless of its biological relevance.

2. **Is inhibition (or degradation, or blockade) of this protein safe?** A target expressed ubiquitously across normal tissues — particularly the heart, brain, and kidney — carries an intrinsic on-target toxicity risk. A target that is essential for the survival of normal cells (not just cancer cells) will produce a therapeutic window too narrow for clinical development.

3. **What is the right therapeutic modality?** Small molecules, antibodies, PROTACs, peptides, and oligonucleotides exploit different target properties, have different tissue access profiles, manufacturing costs, and clinical precedent. Choosing the wrong modality wastes 3–8 years of downstream development.

Phase 3 answers a fourth question: **given the validated target and its modality assessment, which downstream design branches should be opened, and in what order?**

This protocol describes the data sources, biological reasoning, and computational logic underpinning both phases.

---

## 2. Phase 2: Data Sources and Their Biological Roles

### 2.1 DepMap CRISPR Chronos — Essentiality Profiling

**Source:** `Databases/depmap/CRISPRGeneEffect.csv`
**What it measures:** The Chronos score quantifies how much a genome-wide CRISPR knockout of a gene reduces cell fitness across ~1,000 cancer cell lines. Chronos = 0 means the knockout has no effect; Chronos = −1 means the knockout kills the cell as effectively as knocking out an essential housekeeping gene (reference level). Values below −0.5 are typically considered essential.

**Biological interpretation in drug discovery:**

The essentiality profile is indication-type-dependent in a way that is fundamental to the biology:

*In oncology:* The therapeutic goal is selective killing of cancer cells while sparing normal tissue. A gene with Chronos = −0.8 specifically in pancreatic cancer cell lines and Chronos = 0 in normal fibroblasts is an ideal oncology target — it is selectively essential for tumour survival. Conversely, a gene with Chronos = −1.5 across all 1,000+ cell lines (pan-essential) would kill both cancer and normal cells — it is therapeutically unusable.

*In non-oncology:* A gene that is essential for cancer cell survival is often essential for normal cell survival too. In a chronic indication like Parkinson's disease, the ideal target is expressed in the relevant tissue (dopaminergic neurons) but not essential for broad cellular function — its loss specifically disrupts the disease mechanism. Core-essential genes in non-oncology contexts (`high_tox_flag = True`) carry a near-prohibitive toxicity burden.

**The Chronos gate for PROTAC modality (critical design decision):**

Targeted protein degraders (PROTACs) are appropriate when a protein is expressed and active in a pathological way, and when direct inhibition is insufficient (gain-of-function mutant, scaffolding function, resistance to inhibitors). However, the protein must be *present and active* for degradation to have any therapeutic effect.

In oncology, a protein with Chronos ≥ −0.20 in cancer cell lines is non-essential — cancer cells survive its loss. This can mean one of two things: (a) the protein has already been lost (loss-of-function tumour suppressor), or (b) the protein is dispensable in the cancer context. In either case, deploying a PROTAC that degrades it further is therapeutically inert at best and counter-productive at worst. For loss-of-function tumour suppressors — the CDKN2As, the SMAD4s — the protein is already absent or functionally compromised in the tumour. A PROTAC that removes the residual fraction provides no therapeutic benefit and degrades the cell's remaining growth control.

This is the core biological rule encoded in the Chronos gate:

```
In oncology: if chronos > -0.20 → PROTAC score ≈ 0
```

This does not require a curated tumour suppressor gene list. The signal is in the data.

### 2.2 Structure Acquisition Waterfall

**Sources (in priority order):**
1. AlphaFold Database (AFDB) — instant, covers ~98% of human proteome, REST API
2. RCSB PDB — experimental structures where available, REST API
3. ESMFold NIM — for novel or recently characterised proteins (requires NIM_API_KEY)

**Why AFDB is the primary source:**

For drug discovery purposes, AlphaFold v2 structures are now considered production-quality for well-folded domains (pLDDT > 70). The pLDDT (predicted local distance difference test) is AlphaFold's own confidence metric: values > 90 indicate backbone positions predicted with near-crystallographic accuracy; values < 50 indicate intrinsically disordered regions where no stable conformation exists.

The structure source determines what confidence to place on the pocket detection output:
- PDB (experimental): highest confidence; resolution typically 1.5–3.0 Å
- AFDB pLDDT > 90: reliable for pocket detection and docking
- AFDB pLDDT 70–90: usable with caveats; side-chain placement uncertain
- AFDB pLDDT < 70: disordered region; fpocket pockets from this region are artefacts

**pLDDT < 70 triggers the disordered protein handling:**
Intrinsically disordered proteins (IDPs) and disordered regions cannot be targeted by conventional SM docking. The therapeutic approach shifts to: identify ordered domains that do exist (pLDDT > 70 sub-regions), consider PROTAC (if the disorder reflects GoF context), consider peptide mimetics of disordered binding interfaces, or route to the oligonucleotide branch (target the mRNA instead).

BRCA1 exemplifies this: AFDB pLDDT = 42 globally. The protein is largely disordered. Phase 2 correctly produces a low SM druggability score and routes toward PROTAC/peptide.

### 2.3 Pocket Detection — fpocket 4.0

**Source:** fpocket 4.0 (`~/.local/bin/fpocket`)

**What fpocket does:** fpocket uses Voronoi tessellation of the protein surface to identify concave regions large enough to accommodate a drug-like molecule. Each pocket is characterised by:
- **Drug Score (druggability):** A composite metric trained on known drugged vs. undrugged pockets. Values > 0.5 indicate "druggable" by convention; the original training AUROC was 0.89.
- **Pocket volume:** Larger pockets (> 300 Å³) generally accommodate more drug-like molecules.
- **Center of mass coordinates:** Used by the UI to overlay a sphere on the 3D structure viewer.

**Why pocket detection gates the small-molecule branch:**

Structure-based druggability is the primary gating criterion for small-molecule design. A protein with no concave surface — flat protein-protein interaction interfaces, fully convex extracellular domains — has no cavity for a small molecule to occupy. Attempting SM design against such a target wastes the entirety of Phase 5 (typically 8h+ of generative chemistry and docking computation).

The pocket score also informs the PROTAC decision. A partial pocket (druggability 0.2–0.5) is insufficient for SM inhibition but provides a starting point for E3 ligase warhead design — PROTACs can engage a shallow groove as a molecular tether, relying on the PROTAC's bifunctional geometry rather than deep burial in the pocket. This is why KRAS, with its relatively shallow Switch-II pocket, became a PROTAC target alongside SM inhibitors.

**OT tractability as pocket proxy when fpocket has not run:**

In practice, Phase 2 runs fpocket only when an AFDB/PDB structure is available and downloadable. When a target is processed without a structure download (network unavailable, timeout), the code uses OT tractability × 0.7 as a conservative proxy for max_druggability. This is scientifically justified because OT tractability encodes the existence of approved SM drugs (tractability = 1.0 → sotorasib for KRAS) or clinical SM candidates (0.5–0.9), which are themselves evidence that a pocket was found by medicinal chemists. The 0.7 discount factor reflects that OT tractability is a literature proxy, not an independent structural measurement.

### 2.4 AlphaMissense — Variant Pathogenicity

**Source:** `Databases/alphamissense/am_gene_stats.parquet` (gene-symbol indexed, pre-aggregated)

**What AlphaMissense scores:** AlphaMissense (Cheng et al., Science 2023) is a deep learning model trained on protein structure, evolutionary conservation, and functional annotations that predicts the pathogenicity of every possible single amino acid substitution in the human proteome. The score (0–1) reflects the probability that a missense variant causes disease-like effects.

**Phase 2 uses two pre-computed statistics:**
- `am_mean_pathogenicity`: mean score across all possible missense variants — reflects overall structural constraint (highly constrained proteins tend to have high mean pathogenicity)
- `am_high_path_fraction`: fraction of variants with AM ≥ 0.80 — captures the proportion of positions where any change is catastrophic

**Biological interpretation:**

A high `am_high_path_fraction` indicates that many positions in the protein are intolerant of any mutation — the protein is structurally and functionally brittle. This correlates with two drug-relevant properties:

1. **Structural stability:** Brittle proteins tend to have well-folded, compact structures with tightly packed cores — properties associated with clean pockets and successful crystallography. Proteins with low AM constraint tend to be flexible and dynamic.

2. **Functional hotspots:** For oncoproteins (KRAS, PIK3CA), high AM fraction reflects the existence of well-characterised oncogenic hotspot mutations (G12C, H1047R) — positions where specific substitutions are pathogenic and which define the druggable cavity structure.

**Important caveat — AM does not distinguish GoF from LoF:**

AlphaMissense scores all variants as "pathogenic" regardless of direction. SMAD4 has AM high_path_fraction = 0.63 because loss-of-function SMAD4 mutations are pathogenic (they break the tumour suppressor). KRAS has AM high_path_fraction = 0.66 because gain-of-function KRAS mutations are pathogenic (they constitutively activate signalling). The score is the same for both mechanisms but the therapeutic implication is opposite.

This limitation is mitigated by the Chronos gate: the PROTAC scoring considers Chronos before applying any AM boost, ensuring that high AM fraction alone cannot incorrectly elevate a LoF target to PROTAC primary.

**Score boost:** When `am_high_path_fraction ≥ 0.15`, a +0.05 validation score boost is applied. At ≥ 0.25, the boost is +0.10. This reflects that constraint and hotspot density are independent positive signals for target quality — they are additive with, not substitutes for, the other scoring components.

### 2.5 GTEx — Tissue Expression and Safety

**Sources:**
1. GTEx REST API (v2, v8 dataset) — per-tissue median TPM across 54 tissues (primary)
2. `Databases/gtex/gtex_gene_stats.parquet` — global `gtex_log_mean_tpm` + `gtex_pct_expressed` (fallback)

**What tissue expression tells us:**

*Tissue of interest expression:* A drug target must be expressed in the tissue where the disease manifests. A gene with 0 TPM in pancreatic exocrine tissue is not a pancreatic cancer target regardless of its genetics. The `tissue_of_interest` parameter from RunConfig (e.g., "Pancreas") drives the primary expression lookup.

*Tissue Specificity Index (TSI):* TSI = max_tissue_TPM / sum_all_tissue_TPM. A TSI close to 1.0 means the gene is expressed almost exclusively in one tissue (ideal — minimal off-tissue toxicity). A TSI close to 0 means the gene is broadly expressed (therapeutic window is narrower). KRAS TSI ≈ 0 (broadly expressed across all tissues) — this is expected and not disqualifying because KRAS inhibitors (sotorasib) are given systemically and tolerated, but it does indicate that systemic SM exposure will affect non-tumour cells.

*Critical tissue safety flag:* Expression > 10 TPM in heart, brain, or kidney raises a safety flag. These are the three tissues most associated with mechanism-based toxicity in clinical drug development. The flag does not disqualify a target — it requires a selectivity strategy (cancer-selective dosing, targeted delivery, biologic with cancer-specific conjugation).

**Why GTEx instead of TCGA or CCLE:**

GTEx measures expression in normal human tissue from post-mortem donors under the GTEx consortium's standardised protocol. This is the correct comparison for safety assessment: drug-induced toxicity occurs in normal tissue, not in tumour. TCGA captures tumour expression, which is relevant for efficacy but not for off-target toxicity profiling.

The known limitation: GTEx captures baseline expression but not drug-induced expression changes or tissue-specific protein stability. These would require proteomics data.

---

## 3. Phase 2: The Validation Scoring Model

### 3.1 Feature construction

Seven features are computed from the data sources above and from the Phase 1 evidence trail:

| Feature | Source | Biological meaning |
|---|---|---|
| `druggability` | fpocket max_druggability (or OT proxy) | Probability of finding a drug-like binding site |
| `genetic` | Phase 1 blended GWAS/Jensen/OMIM/OT-GA | Disease-specific genetic and functional evidence |
| `ppi_eigenvector` | Phase 1 STRING degree centrality | Network importance — hubs tend to have more regulatory impact |
| `tractability_ot` | Open Targets tractability score | Clinical precedence: SM, biologic, or other modality approved |
| `essentiality_score` | Derived from DepMap Chronos + indication_type | Directional essentiality score (see §3.2) |
| `expression_score` | Derived from GTEx toi_tpm + critical_tissue_flag | Tissue-appropriate expression |
| `safety_score` | Derived from critical_tissue_flag + high_tox_flag | Absence of prohibitive safety signals |

### 3.2 Directional essentiality scoring

The Chronos value is converted to a directional feature depending on indication type. This is the most nuanced transformation in the pipeline:

**Oncology:**
- Chronos = −1.5 to −0.3: selectively or moderately essential → score increases as Chronos becomes more negative. A gene that kills cancer cells when knocked out is exactly what oncology needs.
- Chronos < −1.5: pan-essential → score = 0.20 (too broad; will kill normal cells too)
- Chronos > −0.3: not essential in cancer → score = 0.25 (dispensable in cancer cells)

**Non-oncology (chronic, acute):**
- High tox flag (core-essential in non-oncology context) → score = 0.10
- Chronos < −0.5 → score = 0.30 (essentiality signals safety risk in non-cancer disease)
- Chronos > −0.5 → score = 0.85 (not essential = safe to inhibit)

**Why this asymmetry is correct:**

In oncology, essentiality in cancer cells is a *positive* signal — you want to hit something the cancer needs. In non-oncology, essentiality in a broad panel of cell lines is a *negative* signal — you want to inhibit something disease-relevant but not broadly required for cell survival. The transformation flips the directionality depending on indication. This is a fundamental pharmacological distinction.

### 3.3 Weighted linear scoring model

The final validation score is a weighted sum:

```
validation_score = Σ_f (feature_value_f × weight_f) + AM_boost + PU_nudge
```

Weights (hand-tuned, pending XGBoost training on ChEMBL labels):

| Feature | Weight | Rationale |
|---|---|---|
| druggability | 0.25 | Most decision-relevant: no pocket = no SM/PROTAC |
| genetic | 0.20 | Disease-specific evidence is the second gate |
| ppi_eigenvector | 0.15 | Network centrality correlates with regulatory impact |
| tractability_ot | 0.12 | Clinical precedence is strong but not sufficient alone |
| essentiality_score | 0.12 | Indication-type-aware direction |
| expression_score | 0.08 | Expression is necessary but rarely discriminating among candidates |
| safety_score | 0.08 | Safety signals gate clinical progression |

**SHAP attributions:** For each target, signed per-feature contributions (feature_value × weight − base_rate × weight) explain which inputs drove the score. This satisfies the evidence-first design axiom: every validation score can be audited back to its constituent biological evidence.

**Known limitation:** Weights are not empirically trained (see Bottleneck H5). The PRD specifies an XGBoost model trained on STRING centralities + DepMap labels with target AUROC ~0.93. `Databases/chembl/chembl_37.db` provides the approval labels. This is the next engineering priority for Phase 2.

---

## 4. Phase 2: Tractability Assessment and Modality Scoring

### 4.1 Modality biology primer

Each therapeutic modality exploits different protein and cellular properties:

| Modality | Target requirement | Cellular requirement | Best for |
|---|---|---|---|
| Small molecule (SM) | Druggable pocket (> 300 Å³, drug score > 0.5) | Intracellular or membrane-accessible | Enzymes, GPCRs, intracellular kinases |
| Antibody (AB) | Accessible extracellular surface or ECD | Extracellular or membrane-bound | Secreted proteins, receptor ECDs, cell-surface antigens |
| PROTAC | Protein present and active; partial binding surface | Intracellular (E3 ligase must be co-localised) | GoF oncoproteins, undruggable TFs, SM-resistant mutants |
| Peptide | PPI interface or small extracellular epitope | Extracellular or accessible interface | PPI disruptors, receptor ligands |
| Oligonucleotide | mRNA expressed in accessible tissue | Any (for ASO/siRNA); specific (for splice-switching) | mRNA-druggable targets, LoF supplementation |

### 4.2 Localisation inference

Cellular localisation determines which modalities are physically accessible. In Phase 2 we infer localisation from two signals:

**Signal 1 — Pocket evidence:** If fpocket detected a druggable pocket OR the OT tractability proxy exceeds 0.5, the protein has an accessible interior cavity. This implies intracellular or membrane-bound context.

**Signal 2 — OT tractability pattern:** If OT tractability ≥ 0.7 but no druggable pocket exists (max_druggability < 0.5), the clinical precedence likely comes from an approved biologic — indicating extracellular or membrane-surface access. The archetype: HER2 (ERBB2), OT tractability = 1.0 (trastuzumab, pertuzumab approved), but the extracellular domain has no SM pocket — correctly routed to AB primary.

**Why not use a curated localisation database:**

Subcellular localisation databases (UniProt, HPA) are available and accurate for well-characterised proteins. However, the tractability + pocket combination provides a data-driven localisation inference that is:
1. Directly tied to druggability evidence, not just annotation
2. Resilient to annotation gaps (Tdark proteins have no localisation annotations)
3. Self-consistent: it routes to the modality that already has clinical precedence, which is the lowest-risk starting point

In future implementations, DeepTMHMM (membrane topology) and HPA subcellular localisation annotations will be integrated as primary signals with this heuristic as fallback.

### 4.3 The PROTAC Chronos gate in detail

This is the most biologically nuanced rule in the pipeline and merits detailed justification.

**The therapeutic context for PROTACs:**

PROTACs (PROteolysis TArgeting Chimeras) recruit an E3 ubiquitin ligase to the target protein, tagging it for proteasomal degradation. They are therapeutically appropriate when:

1. **The target is present and pathologically active** — degrading an absent or already-degraded protein accomplishes nothing.
2. **The target's pathological activity is due to its presence** (gain-of-function, overexpression, constitutive activation) — not its *absence*.
3. **Direct inhibition is insufficient** — the target has a scaffolding function, an SM-resistant mutation, or is undruggable by conventional means.

**Why Chronos gates PROTAC eligibility:**

DepMap Chronos measures the effect of CRISPR knockout across hundreds of cancer cell lines. In an oncology context:

- Chronos = −0.52 (KRAS): knocking out KRAS reduces fitness in cancer cells. KRAS is required for cancer cell survival. The protein is present, active, and needed — PROTAC is therapeutically rational.
- Chronos = −0.06 (SMAD4): knocking out SMAD4 barely affects cancer cell fitness. Either SMAD4 is already lost/inactivated in these lines (as it typically is in pancreatic cancer — 55% of PDAC cases have SMAD4 loss) or the cells have found bypass mechanisms. Deploying a PROTAC to degrade SMAD4 further removes what little growth suppression remains. This is therapeutically counterproductive.
- Chronos = +0.15 (CDKN2A): knocking out CDKN2A slightly *improves* cancer cell fitness. CDKN2A (p16) is a tumour suppressor whose loss accelerates the cell cycle. In PDAC, CDKN2A is homozygously deleted in > 80% of cases — the protein is already absent. A PROTAC targeting it degrades nothing in the tumour and removes growth control in normal cells.

**The gate threshold (Chronos > −0.20 → PROTAC near-zero):**

The −0.20 threshold was calibrated so that:
- KRAS (−0.52): passes gate ✓
- PIK3CA (−0.44): passes gate ✓
- BRCA1 (−0.46): passes gate (borderline — BRCA1 dominant-negative mutants are a real PROTAC target space)
- SMAD4 (−0.06): fails gate ✓
- CDKN2A (+0.15): fails gate ✓

A target that fails the Chronos gate receives PROTAC score ≈ 0.05–0.30 (not fully zeroed, to allow the LLM gate 2.8 to override in exceptional cases with documented reasoning), and peptide/oligo scores dominate instead.

**Biological exceptions not yet encoded:**

- **Dominant-negative mutants of TSGs:** A BRCA1 missense mutation that produces a protein that actively *inhibits* wild-type BRCA1 function (dominant-negative) would make a PROTAC of the mutant protein therapeutically rational. This requires allele-specific PROTAC design and cannot be inferred from bulk Chronos data. Currently unimplemented; the LLM gate 2.8 should catch these in clinical review.
- **Non-oncology PROTAC targets:** In neurodegenerative diseases, pathological protein aggregates (tau, alpha-synuclein) are constitutively active nuisances — PROTAC/degrader approaches are rational but the Chronos signal from cancer cell lines is irrelevant. For non-oncology indications, the Chronos gate is relaxed and pocket evidence + variant load are the primary PROTAC signals.

---

## 5. Phase 3: Modality Selection and Branch Routing

### 5.1 The scientific function of Phase 3

Phase 3 is conceptually simple but scientifically critical: it translates the modality assessment (which drug class makes most sense) and the run intent (repurposing vs. de novo design) into an explicit routing decision that determines which of Phases 4, 5, and 6 are executed, and in what order.

This decision has major resource implications:
- Phase 4 (drug repurposing): ~2h, inexpensive, uses existing clinical data
- Phase 5 (de novo small molecule): ~8h, GPU-dependent, generative chemistry
- Phase 6 (de novo biologic): ~4h, structure prediction + developability scoring

Opening the wrong branch wastes compute time and produces scientifically irrelevant candidates.

### 5.2 Repurposing priority from clinical precedence

The repurposing priority flag determines how Phase 4 is approached:

| Priority | OT tractability proxy | Clinical stage | Phase 4 strategy |
|---|---|---|---|
| HIGH | ≥ 0.90 | Approved drug exists | Skip LINCS sweep; dock known approved structures directly |
| MEDIUM | ≥ 0.70 | Phase 2/3 candidate | Run LINCS sweep + dock approved structures; flag as competitive indication |
| LOW_CLINICAL | ≥ 0.50 | Phase 1 candidate | Run LINCS sweep; note Phase 1 failure reasons (informs Phase 5/6 design) |
| LOW | < 0.50 | No clinical precedence | Full LINCS/CLUE sweep; treat as de novo target for repurposing purposes |

**Scientific rationale for the HIGH skip:**

For targets with approved drugs (KRAS: sotorasib, adagrasib; ERBB2: trastuzumab, lapatinib), the LINCS transcriptional signature sweep is unnecessary. LINCS identifies drugs that produce similar transcriptional profiles to the disease signature — its primary value is finding repurposing candidates for targets with no known drugs. When approved drugs already exist, Phase 4 should focus on comparative docking of all approved agents against the target structure, assessing fitness for the specific disease indication, and identifying any resistance-relevant variants.

### 5.3 Intent mode routing

The `intent_mode` parameter set in RunConfig determines the branch structure:

**explore (default):** Phase 4 always executes (cheap, high information value regardless of priority). The de novo branch (P5 or P6) is opened based on primary modality. If budget allows and a secondary modality exists with score ≥ 0.5, both P5 and P6 may be opened in parallel.

**repurpose:** No de novo branches opened. All targets route exclusively to Phase 4. This is appropriate when the clinical constraint is to find an existing approved or late-stage compound rather than design a new molecular entity.

**de_novo:** Phase 4 is skipped entirely. All targets route directly to P5 (SM/PROTAC primary) or P6 (AB/peptide primary). This is appropriate for academic targets or pathogen targets where no existing compounds are expected to be active.

### 5.4 The grey-zone LLM gate

When the top two modality scores are within 0.10 of each other, the rule engine's deterministic output is unreliable — a small change in any input feature would flip the primary modality. These cases are routed to the LLM gate (`3_modality_greyzone`) which is prompted with:
- All modality scores and their gap
- Structure confidence (pLDDT)
- Max pocket druggability
- Essentiality (Chronos)
- Critical tissue flag
- Validation score

The LLM outputs a JSON decision with confidence. Decisions with confidence ≥ 0.65 override the rule-engine primary. All LLM decisions are logged to the `decisions` table for auditability and display in the AI Decision Rail.

---

## 6. Validation Results (2026-06-03)

### 6.1 Benchmark targets and expected outputs

The following six targets from existing Phase 1 runs were used to validate the pipeline. Expected outputs are defined by published pharmacology:

| Target | Disease | Key biology | Expected primary | Got | Correct? |
|---|---|---|---|---|---|
| ERBB2 | Breast (chronic) | RTK with extracellular domain; trastuzumab approved | AB (with fpocket) | SM (without fpocket) | Directionally correct — resolves when fpocket runs |
| PIK3CA | Breast (chronic) | Intracellular PI3-kinase; alpelisib approved; H1047R GoF hotspot | SM | SM | ✓ |
| BRCA1 | Breast (chronic) | BRCA1 is largely disordered (pLDDT=42); PARP inhibitor context via SL | PROTAC/peptide (not SM) | PROTAC/peptide | ✓ |
| KRAS | Pancreatic (oncology) | G12C/D GoF mutations; sotorasib approved; Chronos=−0.52 | SM | SM | ✓ |
| SMAD4 | Pancreatic (oncology) | LoF TF; lost in 55% PDAC; Chronos=−0.06 | peptide/AB | peptide/AB | ✓ |
| CDKN2A | Pancreatic (oncology) | LoF TSG; homozygously deleted in >80% PDAC; Chronos=+0.15 | peptide/oligo | peptide/oligo | ✓ |

### 6.2 Validation score calibration check

Validation scores correctly rank targets by therapeutic complexity:

```
PIK3CA: 0.79  (approved SM, good pocket, high AM, essential)
ERBB2:  0.76  (approved AB, pLDDT=74, essential in cancer)
KRAS:   0.68  (approved SM, but lower genetic score for this run's disease seeds)
BRCA1:  0.52  (disordered, DNA repair; hard to drug directly)
SMAD4:  0.55  (LoF TF; no pocket; moderate OT tractability)
CDKN2A: 0.27  (LoF TSG; no pocket; no OT tractability; Chronos positive)
```

CDKN2A at 0.27 correctly falls below the default Phase 3 threshold (0.50), signalling that it should not proceed to de novo design. The recommendation for CDKN2A in a pancreatic cancer programme would be: exploit its loss via CDK4/6 inhibitors (palbociclib/ribociclib, targeting the CDK4/6 that CDKN2A normally restrains) — a synthetic lethality approach targeting the pathway partner, not the lost tumour suppressor itself.

---

## 7. Disordered and Dark-Genome Proteins (Subroutine 2.6)

### 7.1 Intrinsically disordered proteins (IDPs)

Approximately 30% of the human proteome is predicted to be intrinsically disordered (> 40% disordered residues by IUPred3). Many disease-relevant transcription factors, signalling hubs, and scaffolding proteins are IDPs. The conventional drug discovery paradigm — find a pocket, design a binder — fails for these targets.

**Phase 2 identifies IDPs by pLDDT < 70.** When the entire AlphaFold structure is low-confidence, the protein may lack stable tertiary structure. The therapeutic strategy shifts:

- *Identify ordered domains:* Many IDPs have short ordered regions (SLiMs — Short Linear Motifs) that mediate key interactions. These can be targeted by peptide mimetics.
- *Consider PROTAC:* If the disordered protein is a constitutively active driver (MYC, MYB), a PROTAC can engage a partial surface even without a deep pocket.
- *Consider oligonucleotide:* If the protein is ordered in its mRNA form (often structured at translation regulatory sites), ASO or siRNA approaches target the transcript rather than the protein.

**Currently implemented:** The Phase 2 scoring already reflects disorder through structure.median_plddt feeding into druggability confidence. Full IUPred3 integration (per-residue disorder scores, ordered domain extraction) is in the implementation roadmap.

### 7.2 Tdark proteins (dark genome)

Pharos TDL classification identifies "Tdark" proteins — those with fewer than 2 publications describing any function and no known ligands. These are the frontier of the dark genome. When a Phase 1 novel hypothesis is Tdark, the validation strategy changes:

- No OT tractability data → tractability_ot = 0
- No clinical precedence → repurposing_priority = LOW
- No ChEMBL data → SM chemical matter unknown
- Literature validation is required before computational investment

Phase 2 flags Tdark targets in the evidence trail. The LLM gate 2.9 will note the speculative nature of the target in its evidence summary. Phase 3 will route Tdark targets to Phase 4 only (with full LINCS sweep) rather than opening expensive de novo design branches.

---

## 8. Connection to Upstream (Phase 1) and Downstream (Phases 4–6)

### 8.1 What Phase 2 receives from Phase 1

Phase 2 reads the `targets` table populated by Phase 1. The critical fields and their Phase 2 use:

| Phase 1 field | Phase 2 use |
|---|---|
| `tractability` | OT tractability proxy for pocket-less druggability; PROTAC SM capping; AB route signal |
| `genetic` | Blended GWAS/Jensen/OMIM score → fed directly into validation scoring as genetic feature |
| `ppi_eigenvector` | STRING degree centrality → network feature in validation score |
| `pu_bio_score` | Biological similarity prior → small nudge (+5%) to validation score for biologically coherent targets |
| `ot_genetic_assoc` | Disease-specific OT signal → independent of pu_bio_score; displayed but not re-scored in P2 |
| `essentiality` | Phase 1 raw DepMap value (single feature) — Phase 2 re-derives direction-aware essentiality_score |
| `seeded` | If True, passes Phase 2 regardless of validation score (user has domain knowledge) |

### 8.2 What Phase 2 produces for Phases 4–6

Phase 2 output in `phase_results.output_json` (phase=2) is the validated_targets list. Each entry provides everything downstream phases need:

- **Phase 4 (repurposing):** `pockets[]` with coordinates + `max_druggability` for docking setup; `structure.pdb_url` for the receptor file
- **Phase 5 (SM design):** Same pocket data + `modality.sm_branch_enabled` flag; SMILES seed if provided
- **Phase 6 (biologic design):** `modality.primary == "AB"` or `"peptide"` flag; `structure.uniprot_id` for epitope identification
- **Phase 3 (routing):** `modality.primary`, `modality.secondary`, `validation_score` for threshold decisions

### 8.3 What Phase 3 produces for Phases 4–6

Phase 3 output in `phase_results.output_json` (phase=3) is the routing list. Each entry contains `branches[]` — the explicit list of downstream phases to execute for this target:

```
["P4_repurpose", "P5_small_molecule"]   → KRAS (SM primary, repurposing HIGH)
["P4_repurpose", "P6_biologic"]         → TGFB1 (AB primary, repurposing HIGH)
["P5_small_molecule"]                   → de_novo mode, SM primary
[]                                      → CDKN2A validation score < 0.3 (below threshold)
```

The orchestrator uses this branch list to decide which Celery tasks to enqueue for each target, enabling per-target parallelism: KRAS can be running P4 and P5 simultaneously while TGFB1 runs P4 and P6.

---

## 9. Known Limitations and Planned Improvements

### 9.1 Tissue expression is global mean without per-tissue breakdown

The `gtex_gene_stats.parquet` fallback provides only a global mean TPM and percent-expressed. Tissue-of-interest expression and critical tissue safety flags are unavailable when the GTEx REST API is unreachable. Fix: download GTEx v9 sample attributes file → precompute `gtex_tissue_medians.parquet` (gene × 54 tissues) once at setup. This is the highest-priority data engineering task for Phase 2.

### 9.2 AlphaMissense fraction conflates GoF and LoF variants

AM pathogenicity does not indicate mechanism of effect. SMAD4 and KRAS both have AM high_path_fraction > 0.6, but for opposite biological reasons. The Chronos gate mitigates this, but does not fully separate the signal. Fix: cross-reference high-pathogenicity variants with ClinVar GoF/LoF annotations or OncoKB oncogenicity calls to distinguish which fraction of high-path variants are activating vs. inactivating.

### 9.3 PROTAC Chronos gate was calibrated on six examples

The gate threshold of −0.20 was calibrated against KRAS, PIK3CA, BRCA1, SMAD4, CDKN2A, and ERBB2. A larger benchmarking set (OncoKB-annotated GoF vs. LoF drivers across multiple indications) is needed to validate that −0.20 is optimal. The PRD target AUROC of ~0.93 for the full validation score requires training against ChEMBL-approved targets.

### 9.4 Disordered protein subroutine is not fully implemented

When `median_plddt < 70`, Phase 2 uses the overall structure result but does not: extract ordered domain boundaries (requires IUPred3), flag transmembrane topology (requires DeepTMHMM), or redirect to PROTAC-only pathway explicitly. The scoring reflects disorder implicitly through low druggability, but the explicit subroutine 2.6 logic is not yet callable.

### 9.5 Validation score weights are not trained

The feature weights in `scoring.py` are hand-tuned. The PRD target AUROC of ~0.93 requires training against binary labels from ChEMBL (approved target = 1, no known clinical compound = 0). `Databases/chembl/chembl_gene_maxphase.parquet` already exists and contains the training labels. This is the highest-priority scientific accuracy improvement for Phase 2.

---

## 10. Data Sources and Reproducibility

| Source | Version | Local path | Licence |
|---|---|---|---|
| DepMap CRISPR Chronos | 22Q4 | `Databases/depmap/CRISPRGeneEffect.csv` | CC-BY 4.0 |
| AlphaFold Database | v4 | REST API (per-protein fetch) | CC-BY 4.0 |
| fpocket | 4.0 | `~/.local/bin/fpocket` | MIT |
| AlphaMissense | hg38 (2023) | `Databases/alphamissense/am_gene_stats.parquet` | CC-BY NC 4.0 |
| GTEx | v11 (2026-05-19) | REST API + `Databases/gtex/gtex_gene_stats.parquet` | dbGaP open summary stats |
| Human Protein Atlas | HPA v23 | `Databases/human_protein_atlas/` | CC-BY 4.0 |
| Open Targets tractability | Live v4 API | Via Phase 1 evidence trail | CC-BY 4.0 |
| ChEMBL | v37 | `Databases/chembl/chembl_37.db` | CC-BY SA 3.0 |

All Phase 2 computations are deterministic given fixed input data versions. The LLM gates are non-deterministic (temperature=0.1) but all prompts and responses are logged to the `decisions` table. Any run can be reproduced with the same database versions and LLM gates can be reconstructed from the logged decisions.

---

*Document maintained alongside `phases/phase2_phase3_summary.md` (operational reference) and `bottlenecks/phase2_phase3.md` (engineering issues).*
*Predecessor: `Scientific Protocol/phase1_target_identification.md`*
