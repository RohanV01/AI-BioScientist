# Scientific Methodology: Phase 5 — De Novo Small Molecule Design

**Document type:** Scientific protocol  
**Version:** 1.0 (2026-06-03)  
**Status:** Production — BRICS path validated; REINVENT4 path activates on installation  
**Implementation:** `src/phases/phase5/`

---

## 1. Scientific Problem Statement

Phase 5 addresses the question: when Phase 4 repurposing fails to identify a suitable approved drug for a validated target, can we computationally design novel small molecules that have never entered clinical development?

This is the hardest problem in computational drug discovery. Phase 4 operates in the space of known chemical matter — it asks whether any existing drug can be repositioned. Phase 5 operates in *a priori* unknown chemical space — it must simultaneously satisfy binding affinity (structural fit to the pocket), ADMET safety (the molecule must be tolerable in humans), and novelty (the molecule must not already be covered by existing patents or clinical development).

The challenge is compounded by the vastness of drug-like chemical space. Estimates place the number of synthetically accessible small molecules (MW < 500, Ro5 compliant) at approximately 10^60 (Bohacek et al. 1996). Even the largest virtual compound libraries contain at most ~10^10 compounds. A generative model that can intelligently navigate this space — rather than exhaustively enumerating it — is the only scalable approach.

Phase 5 uses a two-tier generative strategy: REINVENT4 Mol2Mol (Blaschke et al. 2020) as the primary generator, with BRICS (Degen et al. 2008) as a fully local fallback, followed by multi-stage filtering and structure-based virtual screening using AutoDock Vina (Trott & Olson 2010).

---

## 2. Theoretical Basis: BRICS Decomposition and Recombination

### 2.1 BRICS retrosynthetic rules

BRICS (Breaking Retrosynthetically Independent Chemical Systems) was introduced by Degen et al. (2008) to decompose drug-like molecules into synthetically tractable fragments at bonds that correspond to common medicinal chemistry transformations. The algorithm identifies 16 bond types that map to real synthetic reactions (amide bond formation, Suzuki coupling, reductive amination, etc.) and breaks them to produce fragments with appropriate reactive stubs.

The 16 BRICS rules are derived from a retrosynthetic analysis of 90,000 marketed drugs and compounds from Beilstein's pharmacological registry. Each rule is defined by atom environment SMARTS patterns on both sides of the broken bond, ensuring that the produced fragments are:
1. **Synthetically meaningful:** correspond to real building blocks (aryl halides, amines, acids, boronic acids)
2. **Recombinably valid:** can be reassembled via the reverse reaction

For example, BRICS rule 7 breaks amide bonds (C(=O)N), yielding an acid fragment and an amine fragment — the canonical building blocks for amide coupling chemistry (the most common bond-forming reaction in pharmaceutical synthesis, accounting for ~25% of all reactions in drug production, Roughley & Jordan 2011).

### 2.2 Fragment recombination (BRICSBuild)

`BRICSBuild` enumerates valid reassemblies of the fragment pool by applying the 16 BRICS reaction rules in reverse. Each recombination is validated by:
1. Rule compatibility: fragments can only be joined at matching BRICS reactive stubs
2. Valence checking: RDKit sanitization ensures the resulting molecule is chemically valid
3. (Optional) size filtering: products outside MW [150, 600] are rejected before downstream analysis

The combinatorial explosion is managed by limiting output to `P5_N_GENERATE` SMILES (default 1000). For a pool of 200 fragments, the theoretical number of valid BRICS assemblies exceeds 10^5 — the `BRICSBuild` generator is therefore iterated lazily and halted at the limit.

**Synthetic accessibility implication:** BRICS-derived molecules are not just computationally valid — because they were fragmented at real synthetic reaction points, their assembly from the same fragments is often directly achievable using standard medicinal chemistry (amide coupling, Buchwald-Hartwig amination, etc.). This is a significant advantage over purely topological generative approaches that produce novel but synthetically inaccessible molecules.

### 2.3 Fragment pool composition

The fragment pool is derived from ChEMBL binders with pChEMBL ≥ 7 (IC50/Ki ≤ 100 nM against the target, binding assay type 'B'). The 100 nM threshold aligns with industry standards for "confirmed biochemical hit" (Bleicher et al. 2003, Nature Reviews Drug Discovery). Using only potent binders as seeds ensures that the fragment vocabulary is enriched for pharmacophoric elements that have demonstrated target engagement, not just general drug-like fragments.

---

## 3. Theoretical Basis: REINVENT4 Mol2Mol

### 3.1 Architecture

REINVENT4 (Blaschke et al. 2020; Loeffler et al. 2024) is an autoregressive SMILES-based transformer that generates molecular structures character by character using a learned distribution conditioned on input molecules. The Mol2Mol mode is a sequence-to-sequence transformer (encoder-decoder) that maps an input SMILES string to a distribution over output SMILES strings.

The model is trained on ChEMBL SMILES with a contrastive objective: molecules with similar 2D structure (Tanimoto ≥ 0.5) are treated as positive pairs; dissimilar molecules as negatives. This teaches the model to generate structures that preserve the "molecular shape" of the input while exploring variations — analogous to scaffold hopping in medicinal chemistry.

### 3.2 Difference from BRICS

| Property | BRICS | REINVENT4 Mol2Mol |
|---|---|---|
| Chemical space coverage | Constrained to seed fragment vocabulary | Entire ChEMBL space (learned); genuine scaffold hopping |
| Novelty of output | Typically analogues of seeds | Can generate completely new ring systems |
| Synthetic accessibility | High (fragments from real reactions) | Variable; SA score filter required |
| Diversity | ~5–10 Murcko scaffolds per run | 20–50+ Murcko scaffolds per run |
| Requirement | BRICS in RDKit (no extra install) | `reinvent` binary on PATH |
| Runtime | ~45s for 1000 SMILES | ~5 min (GPU) to 20 min (CPU) |

REINVENT4 is preferred for:
- Targets with > 5 years of medicinal chemistry (exhausted BRICS novelty)
- Novel target classes (where seed fragments are scaffolds of existing drugs that don't bind well)
- When the Phase 5 goal is scaffold diversification rather than optimisation

BRICS is preferred for:
- Rapid turnaround (REINVENT4 not installed)
- Targets where known drug fragments have proven pharmacophores
- When the seed set contains highly potent (pChEMBL > 9) compounds worth exploring analogues of

---

## 4. Drug-Likeness and Novelty Filters

### 4.1 Lipinski Rule of Five (Ro5)

The Rule of Five (Lipinski et al. 2001, Advanced Drug Delivery Reviews) is the original empirical observation from Pfizer's compound database that oral drug candidates passing Phase II clinical trials overwhelmingly satisfy:
- Molecular weight ≤ 500 Da
- ClogP (octanol-water partition coefficient) ≤ 5
- Hydrogen bond donors ≤ 5
- Hydrogen bond acceptors ≤ 10

The rule was derived from 2,245 compounds in the MDDR (Drug Data Report) with at least Phase II activity. It predicts oral bioavailability via passive absorption through the gastrointestinal epithelium. The "≤ 1 violation" implementation (Phase 5 `filters.py:L32`) rather than strict "0 violations" is standard practice: ~10% of approved oral drugs violate exactly one rule (e.g., some macrocyclic kinase inhibitors violate MW; amiodarone violates clogP) but have compensating properties (high permeability, active transport).

**Why Ro5 is a filter, not a design target:** The Ro5 defines a chemical space boundary for passive oral absorption. A molecule can violate all four rules and still be an excellent IV drug (biologics routinely do). Phase 5 applies Ro5 because the `P5_small_molecule` branch implies oral small molecule — candidates selected here will eventually face oral bioavailability optimisation in Phase 7 MPO.

### 4.2 Veber Oral Bioavailability Rules

Veber et al. (2002, Journal of Medicinal Chemistry) extended the Ro5 with a rat oral bioavailability study of 1,100 Pfizer compounds, finding that:
- Polar surface area (TPSA) ≤ 140 Å²
- Number of rotatable bonds ≤ 10

These two descriptors outperformed the original Ro5 in predicting rat oral bioavailability (AUC). TPSA correlates with passive membrane permeability (Clark 1999) — a TPSA > 140 Å² typically means insufficient passive intestinal absorption. Rotatable bond count > 10 correlates with poor membrane permeability and increased conformational entropy (worse entopic binding penalty).

In Phase 5, Veber filters are applied as a combined criterion: both TPSA > 140 AND RotB > 10 must be violated to fail. This is more lenient than strict Veber compliance (drop if either violated) because de novo molecules early in optimisation are expected to be slightly outside Veber bounds — Phase 7 MPO explicitly optimises TPSA and RotB as objectives.

### 4.3 PAINS Structural Alerts

Pan-Assay INterference compoundS (PAINS, Baell & Holloway 2010, Journal of Medicinal Chemistry) are substructural motifs that produce artifactually positive results in biochemical assays via non-specific mechanisms: redox cycling (catechols, hydroquinones), covalent modification of assay proteins (aldehydes, Michael acceptors), fluorescence interference, and metal chelation.

Baell & Holloway identified 480 SMARTS patterns by cross-referencing compounds that showed activity in multiple unrelated biochemical assays (suggesting assay interference rather than specific binding). The original study used six distinct assay types across the NIH Molecular Libraries initiative.

**Why PAINS are a warning, not a hard filter in Phase 5:** Phase 5 generates computational structures not yet tested in any assay. A PAINS alert indicates a *risk of assay interference* when the compound is eventually tested biochemically — it does not mean the compound cannot bind the target. Some approved drugs have PAINS-like motifs (e.g., curcumin contains an enone Michael acceptor; catechol-containing COMT inhibitors are approved). Dropping all PAINS hits would unfairly eliminate legitimate chemical matter. The compound is flagged in the `admet_narrative` for the medicinal chemist to evaluate.

### 4.4 Synthetic Accessibility Score

The SA score (Ertl & Schuffenhauer 2009, Journal of Cheminformatics) estimates synthetic accessibility on a 1–10 scale (1 = trivially easy, 10 = nearly impossible) using a fragment contribution model trained on 12 million ZINC compounds with known commercial availability. The score is based on:
1. **Fragment contributions:** ring systems, functional groups, and side chain fragments are scored by their frequency in commercially available molecules (common = easy)
2. **Complexity penalties:** molecular complexity (stereocentres, fused rings, macrocycles, bridged rings) additively penalises the score

The threshold of SA < 6.0 in Phase 5 corresponds to "moderately complex but synthesisable" — analogous to a natural product derivative or an advanced clinical compound. Phase 1 FDA applications typically have SA scores of 3–5 for their clinical lead structure.

**Calibration check:** Aspirin (SA ≈ 1.0), ibuprofen (SA ≈ 1.3), sotorasib (SA ≈ 4.2), taxol (SA ≈ 8.9). The threshold of 6.0 would accept sotorasib but reject taxol — appropriate for a programme targeting novel chemical matter that must be manufactured at industrial scale.

### 4.5 Quantitative Estimate of Drug-Likeness (QED)

QED (Bickerton et al. 2012, Nature Chemistry) is a composite drug-likeness score that combines eight physicochemical properties (MW, alogP, HBD, HBA, TPSA, rotatable bonds, number of aromatic rings, alerts count) into a single [0, 1] value using a desirability function approach. Each property is scored against its distribution in approved oral drugs (from the Comprehensive Medicinal Chemistry database), and the geometric mean of the eight scores gives QED.

QED = 0.0 means "maximally drug-unlike" (e.g., polyethylene glycol); QED = 1.0 means "maximally drug-like". The median approved drug in the training set has QED ≈ 0.67; Phase 5's threshold of QED > 0.3 is deliberately lenient — it excludes only the most extreme outliers (polymers, inorganic salts, macromolecules that escaped BRICS filtering) while retaining genuinely diverse drug-like scaffolds for Phase 7 optimisation.

A stricter QED threshold (e.g., > 0.6) would unnecessarily bias the output towards conventional drug-like molecules and might penalise novel scaffolds with temporary unfavourable properties that MPO can correct.

### 4.6 Tanimoto Similarity and Novelty Threshold

Tanimoto coefficient (Tc) between Morgan fingerprints (circular fingerprints, Rogers & Hahn 2010) is the standard measure of molecular similarity in chemoinformatics:

```
Tc(A, B) = |FP_A ∩ FP_B| / |FP_A ∪ FP_B|
```

Morgan fingerprints with radius=2 (diameter=4: captures atoms and their 2-bond neighbourhood) at 2048 bits are the industry-standard configuration, established as the optimum trade-off between information content and computational speed in the Daylight ECFP4 benchmarking paper (Rogers & Hahn 2010, Journal of Chemical Information and Modeling).

**Why radius=2:** The 2-bond neighbourhood captures local chemical environments including directly bonded atoms, which is sufficient to distinguish pharmacophoric patterns (e.g., a basic amine vs. an amide vs. a sulfonamide). Radius=3 or higher begins encoding global molecular topology and reduces sensitivity to local pharmacophore differences.

**Why 2048 bits:** At this size, the probability of a bit collision between distinct fragments is < 0.1% for typical drug-like molecules (the bit density is low). Reducing to 1024 bits introduces ~5% collision rate; increasing to 4096 provides minimal improvement at 2× memory cost.

**The new MorganGenerator API** (RDKit ≥ 2024.03) replaces the deprecated `AllChem.GetMorganFingerprintAsBitVect`:
```python
from rdkit.Chem.rdMolDescriptors import GetMorganGenerator
gen = GetMorganGenerator(radius=2, fpSize=2048)
```

**Why Tanimoto 0.7 as novelty threshold:**
Maggiora (2006, Journal of Chemical Information and Modeling) established the "Tanimoto cliff" — the observation that the biological activity vs. Tanimoto similarity relationship shows a discontinuity around Tc = 0.85–0.90 (activity cliffs). Compounds with Tc ≥ 0.85 to a known drug typically share its core pharmacophore and represent analogues, not novel scaffolds. Compounds with Tc < 0.7 to any approved drug are in uncharted territory — genuinely new chemical space.

The 0.7 threshold was chosen conservatively: above this value, the compound is likely a close analogue of a known drug (potentially covered by existing IP or already in clinical development by another group). Below 0.7, the compound is considered novel for the purposes of Phase 5.

**Caveat:** The 0.7 threshold applies to the entire ChEMBL approved drug library, not to drugs against the same target. A compound with Tc=0.72 to metformin (an antidiabetic) but Tc=0.1 to all KRAS inhibitors is novel from the KRAS programme perspective but would be dropped. This is acknowledged as a conservative bias (see `bottlenecks/phase5_phase6.md:H5`).

---

## 5. ADMET Pre-Screening: Local Prediction vs ML Models

### 5.1 hERG cardiotoxicity

The hERG (human ether-à-go-go related gene, KCNH2) channel is a cardiac potassium channel; its inhibition causes QT prolongation and potentially fatal torsades de pointes arrhythmia. hERG inhibition is the most common cause of post-market drug withdrawal (Roden 2004) and is mandated for assessment in ICH E14 regulatory guidelines.

**Phase 5 hERG prediction (local, `admet.py:L45`):** Uses two complementary heuristics:
1. **Structural alerts (Aronov 2005):** 29 SMARTS patterns encoding features associated with hERG binding — basic amines with 3–5 Å separation from aromatic rings, cationic nitrogen with flanking hydrophobicity, and specific heterocyclic motifs identified in X-ray structures of hERG blockers (e.g., PDB 5VA1, 7CN1). These patterns were derived from a training set of 644 hERG active/inactive compounds.
2. **Pharmacophore filter:** logP > 4 AND positive charge count ≥ 1 → increased hERG risk flag. The combination of lipophilicity and positive charge is the canonical hERG pharmacophore (Recanatini et al. 2005).

**Comparison with ML prediction (ADMETlab 3.0):** ADMETlab's hERG endpoint is trained on the ChEMBL hERG dataset (> 10,000 compounds, IC50 < 10 µM as positive). It uses a Chemprop directed message-passing GNN with AUC of 0.87 on held-out test sets. The SMARTS-based approach has AUC of approximately 0.72 on the same benchmark — 0.15 AUC lower, corresponding to ~25% false positive rate at 80% sensitivity operating point.

**Why local heuristics are used:** ADMET-AI (Swanson 2024), a free open-source equivalent, provides trained Chemprop models for 41 endpoints including hERG. It can be installed (`pip install admet_ai`) and provides substantially better predictions. The current implementation uses SMARTS because it requires no additional installation or model download, ensuring zero-configuration deployment. The ADMET-AI integration is the highest-priority upgrade (see `bottlenecks/phase5_phase6.md:H2`).

### 5.2 AMES mutagenicity

AMES genotoxicity testing (in vitro Salmonella reverse mutation assay, Ames 1973) is a regulatory requirement for all drug candidates. Genotoxic compounds are direct carcinogens or mutagens — their presence in a development compound triggers immediate programme termination under ICH S2(R1).

**Phase 5 AMES prediction:** 97 SMARTS structural alerts from Kazius et al. (2005, Journal of Medicinal Chemistry), derived from a training set of 4,337 compounds with AMES results. The Kazius alerts encode major classes of genotoxic electrophiles: aromatic amines (N-hydroxylation to form DNA adducts), nitroaromatics (reductive activation), polycyclic aromatics (intercalation + covalent adduct), alkylating agents (epoxides, N-mustards, aziridines), aldehydes and acrolein derivatives.

Specificity of SMARTS-based AMES prediction: ~73% (Kazius 2005 in-paper validation). A false positive rate of ~27% means roughly 1 in 4 flagged molecules is not actually mutagenic. In Phase 5, an AMES flag raises `critical_count` but does not immediately disqualify unless combined with other critical alerts — the LLM gate provides structural context for interpretation.

### 5.3 Hepatotoxicity

Drug-induced liver injury (DILI) is the leading cause of regulatory drug withdrawal (Watkins 2011, Clinical Pharmacology & Therapeutics). Phase 5 screens for reactive electrophilic groups that can form protein adducts in hepatocytes, leading to immune-mediated or intrinsic DILI.

**Structural alerts assessed (`admet.py:L95`):**
- Michael acceptors (α,β-unsaturated carbonyls, vinyl sulphones)
- Epoxide-generating motifs (arene oxides, terminal alkenes activated by CYP3A4)
- Quinone-forming groups (catechols, hydroquinones → quinone oxidation)
- Reactive acyl glucuronides (carboxylic acids → reactive acyl glucuronide conjugate)
- Isocyanates and isothiocyanates (direct electrophiles)

Based on the DILI benchmark of Xu et al. (2010, Toxicological Sciences) — 234 hepatotoxic vs 223 non-hepatotoxic drugs — structural alert-based DILI prediction achieves AUC ~0.72. ML models (e.g., DILIrank-Chemprop) achieve AUC ~0.81.

### 5.4 BBB permeability (CNS penetration)

CNS penetration is assessed using the Egan egg (Egan et al. 2000, Journal of Medicinal Chemistry): a 2D property-space boundary defined by logP ∈ [-1, +5] and TPSA ≤ 90 Å² that predicts passive CNS penetration. Compounds inside the Egan egg boundary have > 90% probability of CNS penetration in rats.

For non-CNS targets, BBB penetration is not a requirement — it is stored in the evidence trail as a property (not used as a pass/fail filter). For CNS targets (determined from target tissue expression data in Phase 2), the Egan egg boundary serves as a soft preference signal that can be incorporated into Phase 7 MPO as an additional optimisation objective.

### 5.5 Caco-2 permeability (intestinal absorption)

Oral absorption through the intestinal epithelium is proxied by Caco-2 monolayer permeability (Artursson & Karlsson 1991). The physicochemical proxy (TPSA < 120 Å² AND MW < 500) correlates with Caco-2 Papp > 1×10⁻⁶ cm/s at r² = 0.62 (Palm et al. 1997, Journal of Pharmacology and Experimental Therapeutics). It is a coarser predictor than trained ML models but captures the primary determinants of passive paracellular and transcellular absorption.

### 5.6 Aqueous solubility (logS) — Delaney ESOL

Aqueous solubility is a fundamental biopharmaceutical property limiting oral bioavailability (Rule of Solvation, Dressman et al. 2007). Phase 5 uses the Delaney ESOL model (Delaney 2004, Journal of Chemical Information and Computer Sciences):

```
logS = 0.16 - 0.63×clogP - 0.0062×MW + 0.066×RingCount - 0.74×RotBonds
```

Trained on 1,144 compounds, RMSE ≈ 1.1 log units. This model captures the main determinants of solubility: lipophilicity (clogP negatively), molecular size (MW negatively), rigidity (ring count negatively), and flexibility (rotatable bonds, positive proxy for solvation). Compounds with logS < -5 (solubility < 3 µg/mL) are flagged as "poorly soluble" — relevant to formulation viability but not a hard disqualification filter in Phase 5.

### 5.7 ADMET disqualification thresholds: oncology vs chronic indications

The FDA's Oncology Center of Excellence guidance (2013) explicitly acknowledges higher acceptable toxicity thresholds for life-threatening malignancies. Phase 5 implements this through the indication-dependent critical count threshold:

- **Chronic indications** (autoimmune, cardiovascular, neurodegeneration, metabolic): `critical_count > 1` → disqualify. A single critical ADMET alert is acceptable for dose optimisation; two or more indicates a genuinely unsafe compound profile that cannot be optimised away.
- **Oncology:** `critical_count > 2` → disqualify. Oncology drugs routinely have one or two adverse toxicological properties (e.g., cyclophosphamide is directly genotoxic but is clinically used; anthracyclines are cardiotoxic but have clinical utility). Two critical flags trigger disqualification because three simultaneous critical alerts represent a compound with multiple liability dimensions unlikely to achieve an acceptable therapeutic index even in a terminal indication.

The `admet_score` formula:
```
admet_score = max(0.0, min(1.0, 1.0 - 0.3 × critical_count - 0.1 × concern_count))
```

The weight of 0.3 per critical flag ensures that `admet_score ≥ 0.5` (the `scoring.py` threshold) is only achievable with 0 or 1 critical flags. The weight of 0.1 per soft concern (logS, Caco-2, BBB) allows multiple soft concerns to accumulate without immediately failing — they represent optimisable liabilities, not dealbreakers.

---

## 6. Structure-Based Virtual Screening with AutoDock Vina

### 6.1 The Vina scoring function

AutoDock Vina (Trott & Olson 2010, Journal of Computational Chemistry) uses an empirical scoring function trained on X-ray crystallography structures from the PDB Bind database:

```
ΔG_binding = ΔG_gauss1 + ΔG_gauss2 + ΔG_repulsion + ΔG_hydrophobic + ΔG_hbond
```

Where:
- `ΔG_gauss1/2`: steric complementarity (two Gaussians of different widths capture close and medium-range van der Waals)
- `ΔG_repulsion`: hard-sphere repulsion for atomic overlaps
- `ΔG_hydrophobic`: ligand-receptor hydrophobic contact area
- `ΔG_hbond`: hydrogen bond count (geometric criteria)

The scoring function was trained on 1,300 PDB structures with known binding affinities (IC50, Ki, Kd). The training set RMSE was ~2.0 kcal/mol; cross-validation RMSE was ~2.3 kcal/mol. Vina does not model explicit solvation (no water molecules), protein flexibility, or covalent binding — important limitations for Phase 5 de novo molecules that may be optimised for these modes.

### 6.2 exhaustiveness=4 for bulk screening

`exhaustiveness` in Vina controls the number of independent stochastic optimisations performed during docking. Each optimisation run starts from a random ligand pose and performs Monte Carlo basin hopping to find local minima. Higher exhaustiveness increases the probability of finding the global minimum pose.

| exhaustiveness | Typical runtime (small molecule) | Pose RMSE vs crystal | Use case |
|---|---|---|---|
| 4 | ~25–60s | ~1.5–1.8 kcal/mol | Phase 5 bulk screening |
| 8 | ~60–120s | ~1.1–1.3 kcal/mol | Phase 4 known drugs |
| 16 | ~2–4 min | ~0.9–1.1 kcal/mol | Phase 8 shortlist |
| 32 | ~5–10 min | ~0.7–0.9 kcal/mol | Phase 8 final candidates |

For Phase 5, exhaustiveness=4 is the deliberate bulk-screening compromise. The Phase 5 docking score is not a final verdict — it is a `combined_pre8` component that determines which candidates advance to Phase 7 and Phase 8 (where exhaustiveness=32 is used). A ~1.5 kcal/mol error at this stage is acceptable because the error is systematic (consistently applied to all candidates) and the absolute `vina_score ≤ -7.0` gate catches the most unreliable low-affinity predictions.

### 6.3 combined_pre8 weight derivation

The `combined_pre8` weights (0.40 Vina, 0.25 ADMET, 0.20 QED, 0.15 novelty) were derived through a theoretical analysis of what determines hit-to-lead progression success:

1. **Vina_norm (0.40):** Binding affinity is the primary reason a compound advances. A compound with poor predicted binding energy cannot progress regardless of its physicochemical or novelty properties. The 0.40 weight reflects this primacy while acknowledging Vina's ~1.5 kcal/mol uncertainty.

2. **ADMET score (0.25):** ADMET failure is the second most common cause of clinical failure (behind lack of efficacy, which binding affinity proxies). The 0.25 weight gives ADMET enough influence to prevent obviously toxic scaffolds from advancing on binding alone.

3. **QED (0.20):** Drug-likeness predicts whether the compound can be optimised in Phase 7 and eventually become a drug. A compound with QED = 0.3 is at the boundary of drug-like space — it may have one property very far from optimal (e.g., MW = 480 but very high lipophilicity). The 0.20 weight allows QED to break ties between similar-binding ADMET-clean compounds.

4. **Novelty (0.15):** Novelty is a programmatic priority (IP position) rather than a scientific quality measure. A known drug with perfect binding and ADMET would be perfectly valid biochemically — its IP status is the concern. The 0.15 weight ensures that novel compounds are preferred when all else is equal, without dismissing slightly less novel compounds that have other advantages.

**Why a weighted sum rather than Pareto ranking:** At Phase 5, the goal is to identify the top-20 candidates from a field of 50–300 post-filter molecules. A Pareto ranking (non-dominated sorting) would typically produce a large Pareto front (20–50% of candidates are non-dominated) and require a secondary ranking within the Pareto front. The weighted sum collapses the multi-objective problem to a single ranking, which is appropriate for a screening step where the downstream phase (Phase 7 MPO) will perform the proper multi-objective optimisation. A full NSGA-II Pareto ranking is used in Phase 7 where the trade-offs among objectives are the explicit scientific question.

---

## 7. LLM Gate 5.4_admet_context: Scientific Rationale

The LLM gate at step 5.4 serves a function that cannot be accomplished by automated scoring: **contextual interpretation of ADMET flags in the setting of a specific therapeutic programme**.

A Michael acceptor flag on an oncology candidate with a Cys-rich active site (e.g., KRAS G12C) may be a feature, not a bug — many approved covalent oncology drugs intentionally contain Michael acceptors (ibrutinib, afatinib, osimertinib). The automated flag cannot distinguish between an intentional covalent warhead and an undesired reactive electrophile. The LLM, prompted with target mechanism-of-action context, can.

Similarly, a basic amine hERG flag on a compound targeting an intracellular kinase is a structural warning but must be weighed against the compound's otherwise excellent profile. The LLM is prompted to:
1. Confirm whether the flagged motif is a known ADMET liability in the therapeutic context
2. Suggest specific, medicinal-chemistry-grounded structural modifications (e.g., "replace the basic piperidine with a neutral morpholine to reduce pKa below 7 and reduce hERG risk")
3. Estimate the likely impact of suggested modifications on binding (based on known SAR in the literature for the target class)

The LLM suggestions are stored in `evidence_trail.admet_narrative` and are not used in automated scoring — they are advisory outputs for the medicinal chemist reviewing the results.

---

## 8. Downstream connections

| Phase 5 output | Phase 7 consumption | Phase 8 consumption |
|---|---|---|
| `combined_pre8` | Initial Pareto population in GP-UCB MPO | — |
| `smiles` | SMILES string → re-featurised as Morgan FP for GP | Re-docked at exhaustiveness=32 |
| `admet_score` | One of 3 MPO objectives (alongside vina, QED) | — |
| `vina_score` | Initial vina objective in GP | Re-scored with Vina + DiffDock if NIM key |
| `qed` | Initial QED objective in GP | — |
| `admet_narrative` | Passed to LLM for modification rationale | — |

---

*Document maintained alongside `phases/phase5_summary.md` (operational reference) and `bottlenecks/phase5_phase6.md` (engineering issues).*
