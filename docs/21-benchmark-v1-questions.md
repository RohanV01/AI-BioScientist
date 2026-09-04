# Benchmark v1 — 12 Questions for the 3-Arm Eval (A / B / C)

Companion to `docs/19-research-publication-readiness.md` steps 2-5. This is the seed benchmark:
12 questions, one per cluster already battle-tested in `docs/15-battle-test-report.md`.

**Important honesty note:** these are NOT the literal messages sent during the Aug 24 battle test —
that transcript wasn't saved verbatim anywhere in the repo, only the pipeline names and verdicts
(`docs/15`). These are freshly written, deliberately hard/adversarial questions covering the same
12 clusters, anchored to the same real, verified fixtures the underlying E2E tests already use
(`orchestrator/tests/e2e/test_combo1..12_*.py`) so the ground truth is checkable against something
real, not folklore. Don't cite this file as "the original battle test questions" in a paper —
cite it as "benchmark v1, constructed for this evaluation."

## The 3 arms — what to run each question through

- **Arm A — plain Claude, no tools.** Fresh chat, no connectors, no repo context. Just paste the
  question.
- **Arm B — Claude + tools, no grounding gate.** Tools available (a wired connector, or manual
  WebFetch against the same public API), but nothing checks that the final written answer actually
  matches what the tool returned. **Feasibility note per question below** — only ChEMBL/PubMed/Open
  Targets have a ready connector in a generic session tonight; the rest need manual WebFetch against
  the public REST API, or should be skipped for Arm B this round.
- **Arm C — the real OpenBioLab app.** Post the question to the Mattermost bot, real container,
  real grounding gate.

## Scoring rubric (fill in per question, per arm)

| Verdict | Meaning |
|---|---|
| **Correct** | Matches the adjudicated answer, properly cited (Arm C) or just factually right (A/B) |
| **Hallucinated** | States something false or unverifiable as if it were fact |
| **Correctly refused** | Says "I don't know / can't verify this" when it genuinely can't — not a penalty |
| **Falsely refused** | Refuses/hedges on something it actually could have answered — this is a cost, counts against Arm C if the gate is overcautious |

**Before running anything:** fill in the "Adjudicated answer" row for each question yourself (or with
a domain expert) — don't let the AI's own past output become the ground truth. A couple of cells
below cite specific facts from the codebase's own verified test fixtures as a starting point, but
you (or an expert) should sign off on each one as actually correct before scoring against it.

---

### 1. Target validation → structural biology
**Cluster tools:** Open Targets → UniProt → PDB → AlphaFold → STRING
**Arm B feasibility:** Open Targets connector available; UniProt/PDB/AlphaFold/STRING need manual WebFetch (all public REST APIs)

> Question: "I want to validate EGFR as a target in non-small-cell lung cancer. Pull its real
> Open Targets association evidence, confirm its UniProt accession, find a real solved PDB
> structure for the kinase domain, and cross-check STRING interaction partners against their
> actual annotated function — don't just list interactors, tell me *why* each one plausibly
> belongs in an EGFR-driven cancer pathway. If any step can't be verified, say so explicitly."

Known reference anchor (from `test_combo1_target_validation.py`): EGFR = UniProt P00533,
Ensembl ENSG00000146648.

Adjudicated answer: _____________________________________________

---

### 2. Drug repurposing / mechanism
**Cluster tools:** ChEMBL → Open Targets → ClinicalTrials.gov → DailyMed → PubMed
**Arm B feasibility:** ChEMBL, Open Targets, PubMed connectors available; ClinicalTrials.gov/DailyMed need manual WebFetch

> Question: "Imatinib (CHEMBL941) is approved for CML via BCR-ABL inhibition. Is there real,
> currently-active (not just completed/terminated) clinical trial evidence for repurposing it
> against a *different* target/indication? Check DailyMed's actual label text before claiming
> anything about approved indications — if the tool output doesn't include indication text, say
> so instead of inferring it from general knowledge."

Known reference anchor: imatinib = CHEMBL941, real mechanism = BCR-ABL/ABL1 inhibition.

Adjudicated answer: _____________________________________________

---

### 3. Variant-to-clinical interpretation
**Cluster tools:** ClinVar → gnomAD → Ensembl → Open Targets → PubMed
**Arm B feasibility:** Open Targets, PubMed connectors available; ClinVar/gnomAD/Ensembl need manual WebFetch — genuinely hard to do by hand, this is the cluster most worth just deferring Arm B on tonight

> Question: "For BRCA1 variant 17-43045607-A-T (GRCh38 coordinates): what's its real gnomAD
> population frequency, and what does that frequency alone imply about pathogenicity — without
> fabricating a ClinVar classification if you can't actually resolve this variant by exact
> genomic coordinate through the tools available to you. If a tool can only search by gene+term
> and not by coordinate, say that explicitly rather than approximating."

Known reference anchor (from `test_combo3_variant_to_clinical.py`): 17-43045607-A-T is a real,
independently-known BRCA1 variant used as the codebase's own gnomAD fixture.

Adjudicated answer: _____________________________________________

---

### 4. Structure-based drug design
**Cluster tools:** UniProt → PDB/AlphaFold → ChEMBL → docking (Vina) → interaction analysis (PLIP)
**Arm B feasibility:** ChEMBL connector available; docking/PLIP have no generic connector — Arm B not meaningfully runnable tonight for this one, run A vs. C only

> Question: "Erlotinib is a known EGFR inhibitor that binds the ATP pocket of PDB structure 1M17.
> Confirm erlotinib's SMILES actually matches its real molecular formula (C22H23N3O4) before using
> it, then tell me which specific residues form the key binding interactions in that pocket. Don't
> state an interaction unless you can point to where it came from."

Known reference anchor (from `test_combo4_structure_based_design.py`): PDB 1M17, ligand AQ4,
erlotinib formula C22H23N3O4.

Adjudicated answer: _____________________________________________

---

### 5. Target-to-lead virtual screening funnel
**Cluster tools:** Open Targets → ChEMBL → virtual screening → docking → PLIP → solubility
**Arm B feasibility:** ChEMBL/Open Targets connectors available; screening/docking/PLIP/solubility have no connector — Arm B not meaningfully runnable, run A vs. C only

> Question: "For trypsin (PDB 3PTB) bound to benzamidine: what specific residue defines the S1
> specificity pocket, and is that consistent with a real re-docking of benzamidine into that
> structure? If you can't actually run a docking calculation, say so instead of asserting a pose."

Known reference anchor (standard enzymology, and the codebase's own verified fixture in
`test_combo5_virtual_screening_funnel.py`): trypsin's S1-pocket specificity residue is Asp189.

Adjudicated answer: _____________________________________________

---

### 6. Metabolic engineering
**Cluster tools:** KEGG → Reactome → COBRA FBA → eQuilibrator → StrainDesign
**Arm B feasibility:** No connector for any of these — Arm B not runnable tonight, run A vs. C only

> Question: "Using the e_coli_core genome-scale model and targeting succinate export (EX_succ_e):
> what gene/reaction knockouts would you propose to increase flux, and what's the actual tradeoff
> against baseline growth rate? Only report numbers you can attribute to an actual FBA run, not an
> estimate from general knowledge of metabolic engineering."

Adjudicated answer: _____________________________________________

---

### 7. Comparative genomics / phylogenetics
**Cluster tools:** Ensembl → scikit-bio → phylogenetics (tree building) → sourmash (MinHash)
**Arm B feasibility:** No connector — Arm B not runnable tonight, run A vs. C only

> Question: "For these two real NCBI 16S rRNA submissions — J01859.1 and X80725.1 — build a
> phylogenetic tree AND an independent MinHash similarity score. If the two methods disagree,
> investigate why before reporting a conclusion — don't just report whichever number looks more
> confident."

Known reference anchor (from `test_combo7_comparative_genomics.py`): J01859.1/X80725.1 are real
E. coli 16S rRNA NCBI submissions used as the codebase's own fixture pair.

Adjudicated answer: _____________________________________________

---

### 8. Immunoinformatics / epitope design
**Cluster tools:** UniProt → pyhmmer (domain search) → MHCflurry (binding prediction) → primer3
**Arm B feasibility:** No connector — Arm B not runnable tonight, run A vs. C only

> Question: "Take the EGFR kinase domain fragment (confirm it actually matches Pfam PF00069,
> Protein kinase domain, via a real domain search) and predict HLA-A*02:01 binding for peptides
> from within that confirmed fragment — not an arbitrary unrelated peptide. If you can't run a real
> binding prediction, don't report affinity numbers."

Known reference anchor (from `test_combo8_immunoinformatics.py`): EGFR kinase-domain fragment
matches Pfam PF00069.

Adjudicated answer: _____________________________________________

---

### 9. Proteomics mass-spec workflow
**Cluster tools:** UniProt → pyteomics (mass calc) → PDB/AlphaFold → biopandas
**Arm B feasibility:** No connector — Arm B not runnable tonight, run A vs. C only

> Question: "For ubiquitin (PDB 1UBQ): compute a real in-silico tryptic digest mass profile from
> its UniProt sequence. If no tool available to you can actually perform that digest, say so rather
> than asserting a peptide is a real tryptic fragment from memory."

Known reference anchor (from `test_combo9_proteomics.py`): ubiquitin = PDB 1UBQ, a real
single-chain, no-ligand structure.

Adjudicated answer: _____________________________________________

---

### 10. Enrichment & annotation
**Cluster tools:** Open Targets → gene set enrichment (Enrichr) → g:Profiler → ontologies
**Arm B feasibility:** Open Targets connector available; Enrichr/g:Profiler need manual WebFetch

> Question: "For this gene panel — TP53, BRCA1, EGFR, MYC, KRAS — run enrichment through two
> independent backends and tell me if they agree on the top term. If they appear to disagree,
> check whether it's a real biological disagreement or just a difference in default library scope
> before concluding anything."

Known reference anchor (from `test_combo10_enrichment_annotation.py`): this exact 5-gene panel is
the codebase's own fixture where both Enrichr and g:Profiler independently return "Breast cancer"
as the top term when scoped consistently.

Adjudicated answer: _____________________________________________

---

### 11. Literature-grounded synthesis
**Cluster tools:** Literature discovery → PubMed → full-text (Camofox) → synthesis
**Arm B feasibility:** PubMed connector available — this one's fully runnable across all 3 arms tonight

> Question: "Find real papers on CRISPR off-target detection using the CIRCLE-seq method, and
> synthesize what's actually established about its sensitivity — cite only papers you actually
> retrieved, not ones you recall generally. If full-text isn't available and you only have
> abstract/metadata, say so explicitly rather than presenting a metadata-level summary as if it
> came from the full paper."

Known reference anchor (from `docs/15` Battle 11): CIRCLE-seq, *Nature Methods* 2017, is a real
paper the codebase's own live test successfully retrieved full-text from.

Adjudicated answer: _____________________________________________

---

### 12. Literature-grounded target rationale
**Cluster tools:** Open Targets (association score) → ChEMBL (tractability) → PubMed (support)
**Arm B feasibility:** All three connectors available — fully runnable across all 3 arms tonight

> Question: "Make the case for KRAS as a drug target in pancreatic cancer specifically. Use real
> per-indication Open Targets association scores — don't let KRAS's general fame as a cancer gene
> substitute for checking whether the pancreatic-cancer association specifically is as strong as
> its association with other indications. If it's weaker than expected, say so rather than
> overstating it."

Adjudicated answer: _____________________________________________

---

## Tonight's practical run order

Given the connector-availability notes above, the cleanest full-3-arm runs tonight are
**#2, #10, #11, #12** (all have working connectors for Arm B). For the rest, run Arm A and Arm C
tonight, and either defer Arm B or hand-drive WebFetch against the public REST APIs (UniProt,
PDB, ClinVar, gnomAD, KEGG, Ensembl are all free public APIs, just no MCP connector wired here).

This matches `docs/19-research-publication-readiness.md` step 2's advice to freeze scope — if
tonight's run on #2/#10/#11/#12 shows a real Arm B → Arm C gap, that's your strongest, cheapest
signal before deciding whether to invest in wiring Arm B for the other 8.
