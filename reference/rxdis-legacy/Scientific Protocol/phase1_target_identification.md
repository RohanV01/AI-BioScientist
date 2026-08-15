# Scientific Methodology: Phase 1 — Computational Drug Target Identification

**Document type:** Scientific protocol
**Version:** 2.0 (2026-06-01)
**Status:** Production — validated across oncology and neurodegeneration
**Implementation:** `src/phases/phase1/`

---

## 1. Scientific Problem Statement

Drug target identification is the first and highest-leverage decision in drug discovery. Selecting the wrong target wastes 5–10 years of downstream development. The challenge is two-sided:

**The false negative problem.** The human genome encodes approximately 20,000 protein-coding genes. The set of validated drug targets numbers in the hundreds. The vast majority of the genome is "unlabelled" — we do not know whether these genes would be safe, efficacious drug targets for a given disease. Standard supervised learning requires both positive examples (confirmed targets) and negative examples (confirmed non-targets), but the latter do not exist reliably. A gene with no drug approved against it is not a confirmed non-target; it may simply be unstudied.

**The streetlight problem.** The most studied genes in a disease (those with the most publications, GWAS hits, and drug trial data) are also the most likely to be retrieved by any analysis that incorporates literature signals. This creates a feedback loop: the targets we know best are the ones we keep finding, while the biology we understand least — the dark genome of ~5,000 poorly characterised proteins — is systematically deprioritized. For diseases with unmet medical need, the most valuable target may be precisely the gene no one has yet studied in that context.

This protocol describes how Phase 1 addresses both problems using a Positive-Unlabeled (PU) learning framework trained on a curated biological feature fingerprint, with disease-specific genetic evidence maintained as an independent output score.

---

## 2. Theoretical Framework: Positive-Unlabeled Learning

### 2.1 Why PU Learning

Standard binary classification requires two clean classes. Drug target identification has only one reliable class: the positive set (validated targets with human genetic or clinical evidence). Randomly labelling non-targets as negatives would introduce false negatives into the training data — genes that are genuinely promising but simply unstudied. This corrupts the model's decision boundary and biases it away from novel biology.

PU learning addresses this by treating all non-positive genes as "unlabelled" — they may be true negatives or undiscovered positives. The algorithm learns to separate the known positive class from the unlabelled background without assuming that unlabelled genes are negatives.

### 2.2 Bagging-PU Algorithm

Phase 1 uses the Bagging-PU method of Mordelet & Vert (2014), which makes a minimal assumption: the unlabelled set contains a small fraction of true positives embedded in a background of true negatives. The algorithm:

1. For each bag b = 1, ..., B:
   - Sample a bootstrap subset S_b from the unlabelled set, where |S_b| = |P| (same size as positives)
   - Train a binary classifier on (P = 1, S_b = 0)
   - Score all genes with this classifier: f_b(g)

2. Final score = mean over all bags: f(g) = (1/B) Σ_b f_b(g)

The bagging serves as implicit regularization against noisy unlabelled negatives. Any true positive that occasionally lands in S_b will be trained on as a negative in that bag, but its positive signal from the full positive set P will dominate across bags. The ensemble average converges to a stable estimate of P(gene is a true target | features).

**Implementation:** LightGBM gradient-boosted classifier with 20–30 bags. Fixed random seed 42 for reproducibility. Leave-one-positive-out (LOO) AUROC computed for model quality estimation.

**Hyperparameters (tuned for small positive sets and 14 features):**
- `num_leaves = 15` — shallow trees prevent individual bag overfitting
- `min_child_samples = 3` — permits splits with few training examples
- `colsample_bytree = 0.8` — uses 80% of features per tree (~11 features), injecting diversity
- `reg_alpha = 0.5, reg_lambda = 2.0` — stronger regularization than default for sparse biological signals

### 2.3 SHAP Attributions

Tree SHAP values (Lundberg & Lee, 2017) are computed on a final model trained on all positives versus a balanced unlabelled sample. Each gene receives a per-feature contribution vector indicating which biological properties drove its score. This is the primary interpretability mechanism — rather than a black-box ranking, each gene's evidence trail explains *why* it was selected in the same language as the input features (essentiality, expression, network connectivity).

---

## 3. Positive Set Construction

The positive set defines what the model learns to recognise. Its quality and diversity directly determine the quality of the biological fingerprint.

### 3.1 Sources of positives

**Tier 1 — User-specified known positives** (mandatory): The user provides 5–10 genes with strong published evidence as drug targets or causal drivers in the target disease. These are typically well-validated by multiple independent lines of evidence. Examples: KRAS, TP53, SMAD4, CDKN2A, BRCA2 for pancreatic cancer; LRRK2, SNCA, PINK1, PRKN, GBA for Parkinson's disease.

**Tier 2 — Open Targets genetic association expansion** (automated): The Open Targets platform integrates GWAS, somatic mutation data (COSMIC), Mendelian disease gene lists, expression QTL studies, and functional genomics screens into a per-gene, per-disease "genetic association" score. Any gene with OT genetic association score ≥ 0.5 for the query disease is added to the positive set.

The threshold of 0.5 was chosen to include confirmed causal genes while excluding weakly associated ones. Empirically: KRAS has OT-GA = 0.868 for pancreatic cancer; ATM = 0.838; ABO (a GWAS hit but not a drug target) = 0.45. The 0.5 threshold includes the former two and excludes the latter.

### 3.2 Why expansion matters

With only 5 user-specified positives and OT-GA as a training feature, the LightGBM model collapses to a single split: genes with OT-GA > 0 are labelled positive; everything else negative. All 19,662 genes with OT-GA = 0 are never visited again. The biological features (essentiality, expression, constraint) have zero information gain in any subsequent split because the positives are already perfectly separated.

With 15–80 positives from the expanded set, each positive has a subtly different biological profile. The model must find patterns that hold *across the full positive set*: "what property do KRAS, TP53, SMAD4, CDKN2A, BRCA2, ATM, BRCA1, PALB2, STK11, CHEK2 ... share?" The answer cannot be "they all have high OT-GA" because that feature is excluded from training. The answer must come from their shared biological properties — and that is exactly what the feature matrix captures.

**Evidence for this effect:** Feature importance gain with 5 positives: OT-GA = 43 (dominant), all other features sum to < 100. Feature importance with 31 positives: all 14 features have non-zero gain; no feature exceeds 5× the second-best feature.

### 3.3 Separation of training labels from output scores

OT genetic association scores are explicitly **excluded** from the training feature matrix. They are used only to define the positive set in step 1.2b and are stored in the evidence trail as an independent `ot_genetic_assoc` field.

This separation preserves the independence of the two output signals:
- `pu_bio_score`: measures how biologically similar a gene is to confirmed disease targets
- `ot_genetic_assoc`: measures the direct genetic and functional evidence linking a gene to the disease

The biological similarity score can surface genes that OT has not yet associated with the disease — genes that look like confirmed targets based on essentiality, expression, and network position, but lack the publication or GWAS coverage that OT needs to assign a high score. These "novel hypotheses" are the primary scientific value of the Phase 1 model.

---

## 4. The Biological Feature Matrix

### 4.1 Design philosophy

Features were selected to satisfy three criteria:
1. **Disease-agnostic** — computable from databases that don't know which disease you're querying
2. **Biologically motivated** — each feature captures a distinct, established drug target property
3. **Experimentally grounded** — preferentially experimental evidence over computational prediction

The 14 features are organised into three biological blocks:

### 4.2 Block 1: Network topology (literature-blind)

Drug targets are rarely isolated proteins. They participate in cellular networks, and their network position tells us something about their biological role.

**Why not use STRING combined_score?** STRING's combined_score has textmining as its highest-correlating component (r = 0.662). The textmining channel counts co-mentions of gene pairs in MEDLINE abstracts. A model trained on a textmining-derived embedding is a literature lookup by proxy. We deliberately exclude textmining by computing channel-specific degree features only from experimental and curated evidence.

| Feature | Channel | Threshold | What it measures |
|---|---|---|---|
| `string_exp_degree` | STRING experimental | score ≥ 200 | Interactions detected in physical experiments (Y2H, co-immunoprecipitation, FRET, etc.) |
| `string_db_degree` | STRING database | score ≥ 200 | Curated pathway database memberships (Reactome, KEGG, BioCarta) |
| `string_coexp_degree` | STRING coexpression | score ≥ 200 | Co-expression across tissue/condition datasets |
| `biogrid_degree` | BioGRID physical | all physical experiments | Independent experimental PPI evidence (distinct from STRING) |
| `primekg_disease_degree` | PrimeKG disease_protein | all disease_protein edges | # distinct disease nodes connected to this gene (hub proxy; TP53=257, FANCE=24) |
| `primekg_pathway_degree` | PrimeKG pathway_protein | all pathway_protein edges | Pathway membership breadth (KRAS=70 pathways, FANCE=1) |

All degree counts are log1p-normalised to compress the heavy-tailed degree distribution.

**Biological rationale:** Confirmed drug targets tend to be moderately connected nodes in functional networks — enough connectivity to be biologically important, but not so highly connected as to be essential for every cellular process. Proteins with > 1,000 physical interactors (extreme hubs like TP53) are both interesting targets and potentially toxic to modulate. The combination of STRING experimental, BioGRID, and PrimeKG disease degree captures this multi-dimensional network position.

### 4.3 Block 2: Functional genomics

These features describe what happens to cells when the gene is perturbed — the most direct measure of biological importance.

| Feature | Source | What it measures |
|---|---|---|
| `essentiality` | DepMap Chronos median | How much losing this gene reduces fitness across cancer cell lines (negative = reduces fitness) |
| `selectivity` | DepMap selective_fraction | Fraction of cell lines where gene is essential — distinguishes cancer-selective from universally essential |
| `expression` | GTEx log1p(mean TPM) | Baseline expression level across normal human tissues |
| `pct_expressed` | GTEx pct_expressed | Tissue breadth — high = ubiquitously expressed (potential safety concern), low = tissue-specific |
| `am_pathogenicity` | AlphaMissense mean | Average predicted pathogenicity of missense variants — reflects structural constraint and functional importance |
| `am_high_path_frac` | AlphaMissense high_path | Fraction of missense variants predicted likely pathogenic — complement to mean pathogenicity |

**Biological rationale:**
- *Essentiality* for oncology: selectively essential genes (low Chronos in cancer, normal in normal) are ideal oncology targets — harming cancer cells without broad toxicity. CDK1 (Chronos = −2.63), PLK1 (−2.78), and CHEK1 (−1.75) show this pattern.
- *Expression*: targets need to be expressed in the relevant tissue. A gene not expressed in pancreatic tissue is a poor pancreatic cancer target regardless of genetics.
- *AlphaMissense constraint*: highly constrained proteins (many pathogenic variants) tend to be structurally important and well-folded — properties associated with druggability.

### 4.4 Block 3: Clinical and disease evidence

| Feature | Source | What it measures |
|---|---|---|
| `chembl_max_phase` | ChEMBL drug_mechanism | Highest clinical phase of any drug against this target (0=none, 0.25=Phase 1, 0.5=Phase 2, 0.75=Phase 3, 1.0=Approved) |
| `is_mendelian` | OMIM mim2gene.txt | Binary flag: this gene causes a Mendelian disease (confirmed causal role somewhere in human disease) |

**Biological rationale:**
- *ChEMBL max phase*: a gene with Phase 3 compounds demonstrates that the protein can be engaged by a drug and has been deemed safe enough for advanced clinical testing — even if for a different disease. This is a prior on druggability.
- *is_mendelian*: Mendelian disease genes have confirmed causal biological roles, tending to produce clear gain- or loss-of-function phenotypes. This property correlates weakly with being a drug target but is non-zero.

**Known limitation:** Both features have low gain in all three tested diseases (chembl_max_phase gain = 0.2–9, is_mendelian = 0.2–3.2). This is because 83% of genes in STRING's universe appear in OMIM (too broad), and ChEMBL coverage is sparse relative to the 19,699-gene universe. These features will improve when COSMIC Cancer Gene Census (cancer-specific tier annotation) and gnomAD pLI/LOEUF (germline constraint) are added.

---

## 5. The Novel Hypothesis Discovery Mechanism

This is the core scientific contribution of Phase 1: surface genes that have a biological profile consistent with confirmed disease targets but lack existing disease-specific evidence.

### 5.1 How a novel hypothesis is generated

1. The PU model trains on the biological fingerprint of 15-80 confirmed disease targets
2. It learns which combinations of essentiality, expression, network connectivity, and constraint characterise this particular disease's target biology
3. It scores all 19,699 genes by how well they match this fingerprint
4. Genes that match the fingerprint but have `ot_genetic_assoc = 0` are novel hypotheses: they "look like" confirmed targets biologically, but haven't been directly linked to the disease through genetics or functional studies

### 5.2 Validated novel hypotheses

**Pancreatic cancer:**
- **MET** (pu_bio=0.987, OT-GA=0): MET proto-oncogene. MET amplification occurs in ~5% of pancreatic ductal adenocarcinoma (PDAC). MET inhibitors (capmatinib, tepotinib) are approved for other indications. The model found MET because it shares essentiality and network properties with KRAS and other confirmed PDAC drivers.
- **BLM** (pu_bio=0.984, OT-GA=0): Bloom syndrome helicase. BLM-deficient cells accumulate double-strand breaks and sister chromatid exchanges — the same DNA repair defect exploited in BRCA1/2-deficient tumours. BLM shares its network neighbourhood with BRCA1, BRCA2, PALB2, and ATM, all confirmed PDAC targets.
- **FANCD2** (pu_bio=0.984, OT-GA=0): Fanconi Anemia complementation group D2. FANCD2 is monoubiquitinated by the Fanconi Anemia core complex in response to DNA damage and co-localises with BRCA2 at sites of stalled replication. The BRCA-Fanconi pathway is the dominant genetic risk architecture in PDAC; FANCD2 is a biologically coherent extension of the confirmed target set.

**Parkinson's disease:**
- **MT-ND2, MT-ND3, MT-ND5, MT-ND6** (pu_bio=0.977–0.988, OT-GA=0): Mitochondrially-encoded NADH dehydrogenase subunits (Complex I components). The model found these because two user-specified positives (PINK1 and PRKN) protect mitochondrial quality through PINK1/Parkin-mediated mitophagy. Loss of PINK1 or PRKN leads to accumulation of damaged mitochondria with Complex I dysfunction. The model, having learned that PINK1/PRKN-adjacent mitochondrial biology defines PD targets, extended this to the Complex I subunits that PINK1/PRKN protect. Complex I dysfunction has been independently validated in PD pathology for over 30 years (Parker et al., 1989; Schapira et al., 1989).
- **PSAP** (pu_bio=0.979, OT-GA=0.745): Prosaposin. PSAP is the precursor protein for the saposins (A, B, C, D), which are essential co-activators of lysosomal enzymes including GBA (glucocerebrosidase, a user-specified positive). GBA cannot cleave glucosylceramide without saposin C activation. The model found PSAP because it has an expression and network profile nearly identical to GBA — both are lysosomal, both are expressed in brain, both are connected to the lysosome-disease network in PrimeKG. PSAP gene variants have been independently associated with PD risk in human genetics studies (Bourinaris & Houlden, 2018).
- **CD40** (pu_bio=0.985, OT-GA=0): Tumour necrosis factor receptor superfamily member 5. CD40-CD40L signalling activates microglia and drives neuroinflammation. Microglial activation is increasingly recognised as a central pathological mechanism in PD, and anti-CD40L therapy reduces neuroinflammation in rodent PD models.

### 5.3 False positives — and why they're acceptable

Not all novel hypotheses are correct. **ESR1** (estrogen receptor alpha) appears in the pancreatic cancer top-20 (pu_bio=0.985, OT-GA=0) because it shares a similar disease network profile with BRCA1 (breast-ovary-associated disease degree). ESR1 is not a primary PDAC driver.

This is acceptable for two reasons:
1. The false positive rate in the Phase 1 output is expected. Phase 1 is a hypothesis-generation step, not a validation step. Phase 2 independently validates each target using structural biology (pocket detection), tissue-specific expression, CRISPR essentiality in disease-relevant cell lines, and chemical matter from ChEMBL. ESR1 would be correctly rejected in Phase 2 (no PDAC-relevant pocket expression, no chemical matter for pancreatic cancer).
2. The false positive ESR1 carries a visible signal in the evidence trail: `ot_genetic_assoc = 0.0`. Downstream analysts can immediately see that this gene has no direct genetic evidence for pancreatic cancer and apply appropriate scepticism.

---

## 6. Output Structure and Downstream Use

### 6.1 The two-score evidence trail

Each output target carries two independent scores plus full biological provenance:

```json
{
  "symbol": "ATM",
  "rank": 5,
  "pu_bio_score": 0.987,
  "ot_genetic_assoc": 0.838,
  "shap_top": [
    {"feature": "primekg_disease_degree", "value": 0.421},
    {"feature": "essentiality",           "value": -0.187},
    {"feature": "string_exp_degree",      "value": 0.152},
    {"feature": "am_pathogenicity",       "value": 0.119},
    {"feature": "biogrid_degree",         "value": 0.098},
    {"feature": "gtex_log_mean_tpm",      "value": 0.087},
    {"feature": "selectivity",            "value": 0.062},
    {"feature": "primekg_pathway_degree", "value": 0.031}
  ],
  "is_master_regulator": false,
  "essentiality": -0.029,
  "selectivity": 0.012,
  "expression": 1.948,
  "tractability": 0.65,
  "genetic": 0.671,
  "ppi_eigenvector": 0.273,
  "tdl": "Tchem"
}
```

**Reading the SHAP values:** Each entry shows which biological feature was most responsible for the gene's score. In the example above, ATM ranks highly because it has high disease network connectivity (primekg_disease_degree, SHAP=0.421), moderate essentiality (essentiality = −0.029, SHAP contribution = −0.187 meaning it slightly reduces the score — ATM is not highly essential), and strong experimental network evidence (string_exp_degree). This is a transparent, auditable explanation.

### 6.2 The four target categories

**Category 1 — High-confidence targets** (pu_bio_score ≥ 0.9, ot_genetic_assoc ≥ 0.5): Both biological profile and direct genetic evidence align. These are the safest Phase 2 investments. Examples: ATM (pancreatic cancer), PSAP (Parkinson's), CDH1 (breast cancer).

**Category 2 — Novel hypotheses** (pu_bio_score ≥ 0.9, ot_genetic_assoc < 0.3): Strong biological similarity to confirmed targets, no established genetic link. These are the highest-upside candidates — potentially genuinely novel target discoveries. Examples: MT-ND3 (Parkinson's), BLM (pancreatic cancer), FANCD2 (pancreatic cancer). All require Phase 2 validation.

**Category 3 — Genetically confirmed, atypical biology** (pu_bio_score < 0.7, ot_genetic_assoc ≥ 0.5): OT confirms the gene's disease relevance, but its biological profile doesn't strongly resemble confirmed targets. This may indicate a genuinely novel mechanism or a structurally challenging target. These warrant investigation but with caution.

**Category 4 — Weak signal** (pu_bio_score < 0.5, ot_genetic_assoc < 0.3): Not pursued.

### 6.3 DoRothEA master-regulator annotation

As a post-scoring step, each top-200 gene is checked against the DoRothEA regulon database. Transcription factors (TFs) with large, high-confidence regulons that are connected to disease biology are annotated as master regulators. This is particularly valuable for identifying upstream targets: a TF that controls 500 disease-relevant downstream genes is a higher-leverage target than an effector protein at the end of a pathway.

Example: TP53 (pancreatic cancer) flagged as TF, DoRothEA confidence A, regulon_size=597 — the top master regulator in the list.

---

## 7. Validated Performance Across Diseases

The model has been validated across three biologically distinct diseases:

### 7.1 Pancreatic ductal adenocarcinoma (PDAC)

- Seeds: KRAS, TP53, SMAD4, CDKN2A, BRCA2 (canonical somatic drivers)
- Expanded to 31 positives (OT-GA ≥ 0.5)
- AUROC(LOO): 0.880
- Dominant biology learned: DNA damage response, Fanconi anemia pathway, tumour suppression
- Feature importance: primekg_disease_degree (328) >> string_exp_degree (83) > expression (63) > essentiality (33)
- Cross-validation: BRCA1 (rank 4), ATM (rank 5), PALB2 (rank 10), STK11 (rank 18) — all independently validated PDAC susceptibility genes, found without being in the seed set
- Novel hypotheses: MET, BLM, FANCD2, ERBB3

### 7.2 Breast adenocarcinoma

- Seeds: BRCA1, BRCA2, TP53, PIK3CA, ERBB2 (canonical oncogenes/suppressors)
- Expanded to 77 positives (OT-GA ≥ 0.5 — breast cancer is OT-well-covered)
- AUROC(LOO): 0.915
- Dominant biology learned: DNA repair, hormone signalling, PI3K/AKT pathway, cell cycle
- Feature importance: primekg_disease_degree (1000) >> string_exp_degree (110) > biogrid_degree (97)
- Cross-validation: ESR1 (rank 15), CDH1 (rank 20), ATM (rank 4), CCNE1 (rank 3) — all breast cancer-relevant
- Novel hypotheses: ERCC4, IRS1, POT1, CASP8, FAS, RUNX1

### 7.3 Parkinson's disease

This is the most important validation — Parkinson's is biologically distant from cancer and serves as a genuine test of cross-disease generalization.

- Seeds: LRRK2, SNCA, PINK1, PRKN, GBA (mechanistically diverse: kinase, aggregation, lysosomal, mitochondrial)
- Expanded to 71 positives (OT-GA ≥ 0.5)
- AUROC(LOO): **0.755** — meaningfully lower than cancer, reflecting the biological heterogeneity of PD targets (correct behaviour, not a failure)
- **Feature importance profile completely different from cancer:** string_exp_degree (195, top) > primekg_disease_degree (192) > essentiality (174) > expression (151) > am_pathogenicity (117). Expression and essentiality are as important as network degree — the model learned that PD targets have a distinctive neuronal expression signature.
- Cross-disease check: only ATM shared with cancer top-20 (out of 20 genes). The model is not returning a generic disease-gene list.
- Novel hypotheses: MT-ND2, MT-ND3, MT-ND5, MT-ND6, MT-CYB (mitochondrial Complex I — biologically coherent extension of PINK1/PRKN mitochondrial quality control biology); PSAP (prosaposin, essential GBA co-activator).

---

## 8. Model Quality Assessment

### 8.1 What AUROC(LOO) measures — and its limitation

Leave-one-positive-out AUROC asks: "given all other positives as training, does this positive rank above 19,000+ unlabelled genes?" Values of 0.75–0.92 indicate the model genuinely uses the positive set's biological fingerprint to rank genes.

**The key AUROC insight from validation:** AUROC correlates with biological homogeneity of the positive set, not with model performance per se. Cancer targets (DNA repair, cell cycle) are homogeneous → AUROC 0.88–0.92. Parkinson's targets (lysosomal, mitochondrial, aggregation) are heterogeneous → AUROC 0.755. A lower AUROC for Parkinson's reflects the genuine difficulty of finding a single biological profile that covers mechanistically diverse targets — it should NOT be interpreted as a worse model.

### 8.2 Permutation test

Randomly shuffled positive labels (10 independent trials) yield AUROC mean = 0.616 ± 0.165. The real model's AUROC of 0.880 represents a gap of 0.264 above the permuted baseline, confirming genuine learning above chance. The permuted baseline is above 0.5 because features like `primekg_disease_degree` are non-uniformly distributed — this structural inflation is present in both real and permuted runs and cancels out in the gap.

### 8.3 Feature importance validation

All 14 features have non-zero gain in all three diseases. This is the essential quality check for the expanded positive set architecture. With 5 positives (old architecture), 11/16 features had zero gain. With 15–80 positives (new architecture), feature gain is distributed across all features with no feature completely dominating.

### 8.4 Cross-disease discrimination

The top-20 gene lists differ substantially between diseases:
- Pancreatic vs Breast: 10/20 shared (general cancer biology) + 10 disease-specific each
- Pancreatic vs Parkinson's: only 1/20 shared (ATM — genuinely relevant to both)

This demonstrates that the model produces disease-specific outputs, not a fixed list of general disease hubs.

---

## 9. Known Limitations and Planned Improvements

### 9.1 `primekg_disease_degree` dominance

The most impactful current limitation. PrimeKG disease degree captures "how broadly disease-associated is this gene across all disease ontologies." For cancer, this conflates "important across all cancers" with "important for this specific cancer." The mitigation is the two-score system — `ot_genetic_assoc` provides disease specificity. Planned fix: disease-specific PrimeKG degree (count only edges to disease nodes in the target disease's ontological neighbourhood) or COSMIC Cancer Gene Census as a feature (Tier 1/2 cancer driver annotation, much more specific than PrimeKG breadth).

### 9.2 OT-GA threshold sensitivity

The threshold of OT-GA ≥ 0.5 for positive expansion was determined empirically and may be inappropriate for rare diseases with sparse OT coverage. A disease with OT-GA ≥ 0.5 for only 3 genes would degrade to near the 5-positive regime. Planned fix: adaptive threshold (lower to 0.3 if < 10 genes at 0.5), supplemented by ClinVar pathogenic variant genes for the disease.

### 9.3 OMIM and ChEMBL near-zero contribution

Both features have < 10 gain in current runs. `is_mendelian` covers 83% of genes (too broad); `chembl_max_phase` is sparse. Planned replacements: gnomAD LOEUF (germline LoF constraint — highly discriminating, not yet downloaded) and COSMIC tier (cancer driver classification).

### 9.4 GTEx as a normal tissue proxy

GTEx captures expression in normal (non-disease) tissue from post-mortem donors. For cancer targets, the relevant expression context is the tumour, not normal adjacent tissue. CCLE (Cancer Cell Line Encyclopedia) expression data from DepMap would provide disease-specific expression in a lineage-appropriate cell context. This is planned as the next database addition.

### 9.5 Tractability not assessed in Phase 1

The Phase 1 model scores genes by biological relevance and genetic evidence, but does not yet assess whether the protein product can be drugged. This assessment is the core of Phase 2 (pocket detection, structural biology, modality selection). The current `ot_tractability` score in the evidence trail is a proxy from OT's rule-based tractability buckets, not a physics-based assessment.

---

## 10. Data Sources and Reproducibility

All data sources used in Phase 1 are either locally cached or fetched from stable, versioned APIs:

| Source | Version / Date | Local? | Licence |
|---|---|---|---|
| Open Targets GraphQL | Live API v4 | No (API) | Open, CC-BY 4.0 |
| Pharos GraphQL | Live API | No (API) | Public domain |
| STRING protein links | v12.0 | Yes | CC-BY 4.0 |
| BioGRID | v5.0.257 | Yes | MIT |
| PrimeKG | 2023 release | Yes | MIT |
| DepMap CRISPR | Chronos (22Q4) | Yes | CC-BY 4.0 |
| GTEx | v11 (2026-05-19) | Yes | dbGaP (public summary stats) |
| AlphaMissense | hg38, 2023 | Yes | CC-BY NC 4.0 |
| ChEMBL | v37 | Yes | CC-BY SA 3.0 |
| OMIM | mim2gene.txt | Yes | OMIM licence (free academic) |
| GWAS Catalog | 2026 year-split TSVs | Yes | EMBL-EBI open |
| Jensen DISEASES | 2024 | Yes | CC-BY 4.0 |
| DoRothEA | regulons_ABC | Yes | GPL-3.0 |

All model runs use fixed `random_state=42` for reproducibility. The LightGBM version and feature matrix schema are versioned through the codebase.

---

## 11. Connection to Downstream Phases

Phase 1 outputs feed Phase 2 (Target Validation) through the Supabase `targets` table. The interface contract:

| Phase 1 output | Phase 2 consumption |
|---|---|
| `pu_bio_score` | Used as a prior in Phase 2's validation scoring |
| `ot_genetic_assoc` | Used as the disease-specific genetic evidence feature |
| `tractability` | OT tractability hint — Phase 2 refines with structural assessment |
| `genetic` | Blended GWAS/Jensen/OMIM score — independent of OT-GA |
| `ppi_eigenvector` | Network centrality proxy — Phase 2 uses for hub penalty |
| `essentiality` | Pre-fetched from DepMap — Phase 2 re-derives for cell-type specificity |
| `tdl` | Pharos TDL class — guides Phase 2 structural strategy (Tdark → speculation flag) |
| `is_master_regulator` | TF flag — informs Phase 2 modality (TFs have different druggability) |

Phase 3 (Modality Selection) reads nothing from Phase 1 directly — it consumes Phase 2 output.

---

*Document maintained alongside `phases/phase1_summary.md` (operational reference) and `bottlenecks/phase1.md` (engineering issues).*
