# In-Silico Agentic Drug Discovery Pipeline: Human-Executable Specification v1.0

**Bottom line up front:** This is a deterministic, sequential, human-executable pipeline that takes a disease string as input and outputs (a) a ranked target list with evidence trails and (b) ranked in-silico-validated drug candidates (small molecules and/or biologics) per target, designed to run on a 16 GB RAM / 6 GB RTX 3050 laptop by aggressively routing heavy inference to free or cheap hosted services (NVIDIA NIM, Neurosnap, AlphaFold Server, Google Colab, Modal, RunPod, HuggingFace). Total cash budget for one disease-to-candidate run is targeted at $0–$50 if you stay on free tiers and use hosted endpoints sparingly; $50–$300 if you do extensive MD validation on rented A100s. The architecture is sequential and self-contained per phase; agentification is explicitly out of scope — this is a workflow spec for Claude Code to implement step-by-step.

---

## TL;DR

- **Pipeline shape:** Phase 0 setup → Phase 1 target ID → Phase 2 target validation → Phase 3 modality decision gate → Phase 4 (repurposing) and/or Phase 5 (small molecule de novo) and/or Phase 6 (biologic/peptide de novo) → Phase 7 multi-parameter optimization → Phase 8 in-silico validation gate → Phase 9 output packaging. Each phase has exact JSON I/O contracts so any step is independently testable.
- **Hardware routing rule:** anything ≥12 GB GPU memory or ≥32 GB RAM goes to hosted (NVIDIA NIM free tier for AlphaFold2/OpenFold2/RFdiffusion/DiffDock, AlphaFold Server for AF3, Neurosnap for BoltzGen/Boltz-2/RFdiffusion2/ColabDock, Colab Pro for batch protein folding, Modal/RunPod for short MD). Local 6 GB GPU runs RDKit, AutoDock Vina, fpocket, REINVENT 4 small batches, ProteinMPNN small designs, gmx_MMPBSA, NetworkX, OpenMM minimization/short MD, ADMET-AI distilled, local LLM literature triage.
- **Critical constraint:** BindCraft (per its README, the authors "highly recommend to run it using a local installation and at least 32 Gb of GPU memory"), full RFdiffusion All-Atom, AlphaFold3 local inference, ESMFold-3B local, full Boltz-2 training, and Proteina-Complexa do NOT fit on 6 GB. The pipeline routes them out and never tries to run them locally.

---

## Key Findings

1. **The free-tier hosted compute landscape in May 2026 is rich enough to run this pipeline end-to-end without dedicated GPU rental for most disease inputs.** NVIDIA Build (NIM): the credit-based system was retired in early 2025 and replaced with unlimited free usage at rate limits commonly up to 40 requests per minute (per developer accounts as of April 2026, e.g., Medium @vignarajj: "That credit-based system was fully phased out in early 2025. Today the free tier works on straightforward rate limits…commonly up to 40 requests per minute (RPM)."). NIM hosts OpenFold2, AlphaFold2, RFdiffusion, ProteinMPNN, DiffDock-V2, MolMIM, GenMol, MSA-Search, ESMFold (build.nvidia.com). AlphaFold Server quota progression: 10/day at launch (May 2024) → 20/day → 30/day as of January 2026 (Bonvin Lab tutorial, Jan 2026: "there is a limit of 30 jobs per day (as of January 2026)"), with a 5,000-token cap per job. Neurosnap free tier covers AlphaFold2, BoltzGen, DiffDock-L, RFdiffusion2, GNINA, ColabDock, ProteinMPNN, ImmuneBuilder, and ADMET-AI. ADMETlab 3.0 and SwissADME have free public APIs. Always check AlphaFold DB's 200M precomputed structures before predicting.
2. **Boltz-2 is the most important single tool to integrate** — it replaces multi-day FEP simulations that cost approximately $100 per prediction and took 6–12 hours with a 20-second prediction at "a few cents" on a single GPU, and approaches FEP-grade affinity ranking (per Bio-IT World, Oct 2025: "Boltz-2 dropped the cost from approximately $100 per prediction that took 6-12 hours to just a few cents for a 20-second prediction on a single GPU"). Known caveats from independent evaluations: systematic deviations in ring planarity, chirality, bond lengths in generated poses, and a tendency to flatten affinity variance within a top-100 set. Use Boltz-2 for ranking, never as the sole oracle.
3. **The modality decision gate** fires after target validation and routes on three explicit criteria: (a) druggable pocket with PockDrug probability >0.5 AND fpocket druggability >0.5 → small molecule; (b) intracellular with no pocket but high PPI centrality → PROTAC/molecular glue (bifunctional design in the SM branch); (c) extracellular or membrane-proximal with no pocket → biologic/peptide via BoltzGen or RFdiffusion NIM. Tdark targets with no structure go through AlphaFold DB lookup, then ESMFold via API as fallback.
4. **For drug repurposing, LINCS L1000 / CMap reverse-signature matching has known reproducibility limits** — Lim & Pavlidis (2021) reported only ~17% success rate when CMap1 signatures were used to retrieve themselves from CMap2 — so use it as one signal among three: (1) LINCS reverse signature, (2) ChEMBL approved-drug docking with Vina locally then DiffDock NIM rescoring, (3) PrimeKG drug-disease edge prediction. The CMap 2/LINCS-L1000 corpus contains 591,697 profiles from 29,668 perturbagens across 98 cell lines (Keenan et al., bioRxiv 845693). Triangulate; never trust a single signal.
5. **For biologic design on this hardware, BindCraft is OUT** — the BindCraft README explicitly states: "However, as the pipeline requires significant amount of GPU memory to run for larger target+binder complexes, we highly recommend to run it using a local installation and at least 32 Gb of GPU memory." Viable paths instead: BoltzGen (Stark et al., bioRxiv 2025.11.20.689494: "We introduce BoltzGen, an all-atom generative model for designing proteins and peptides across all modalities to bind a wide range of biomolecular targets" — MIT-licensed, hosted on Neurosnap), OR RFdiffusion NIM (NIM docs: 12 GB GPU minimum on the hosted endpoint with compute capability >7.0, so hosted-only on this hardware) → ProteinMPNN (local OK for designs <150 aa) → AlphaFold2 NIM validation. BindCraft enters only if user pays for Neurosnap or rents an A100 on RunPod ($1.39/hr Community Cloud A100 PCIe per runpod.io/pricing).

---

## Details

### PHASE 0 — System Inputs and Setup

#### 0.1 Primary input

```json
{
  "disease_input": {
    "disease_name": "string (free text)",
    "disease_efo_id": "string|null (e.g., EFO_0000270 for asthma)",
    "disease_mondo_id": "string|null",
    "disease_doid_id": "string|null",
    "icd10": "string|null"
  }
}
```

The pipeline normalizes any free-text disease string to an EFO ID via Open Targets `search` GraphQL query first, then carries the EFO ID as the canonical key.

#### 0.2 Auxiliary inputs (all optional)

```json
{
  "patient_cohort": {
    "expression_matrix": "path/to/tsv (genes × samples)",
    "metadata": "path/to/tsv (sample_id, condition, tissue)",
    "vcf": "path/to/vcf|null"
  },
  "modality_preference": "small_molecule | biologic | peptide | any (default=any)",
  "budget_hosted_usd": "integer (default=25)",
  "target_count_max": "integer (default=20)",
  "candidates_per_target_max": "integer (default=10)",
  "repurposing_enabled": "boolean (default=true)",
  "de_novo_enabled": "boolean (default=true)"
}
```

#### 0.2a Extended run configuration (all optional, serialized to `run_config.json` at Phase 0 and carried through all phases)

**Intent mode** — tells the pipeline which branches to prioritize and how aggressively to prune:

```json
{
  "intent_mode": "explore | repurpose | de_novo (default=explore)"
}
```

- `explore`: broad survey, all modalities, all branches active. Use for a new disease with no prior hypothesis.
- `repurpose`: Phase 4 is primary; Phases 5/6 are lightweight or skipped. Use when you have an approved drug you want validated for a new indication, or when speed > novelty.
- `de_novo`: Phase 4 is a quick check only; full compute goes to Phase 5 or 6. Use when you need a genuinely novel scaffold.

**Indication type** — governs safety weight thresholds throughout Phases 5–8:

```json
{
  "indication_type": "chronic | acute | oncology (default=chronic)"
}
```

- `chronic`: strict hERG, hepatotox, and immunogenicity thresholds; BBB penetration penalized unless CNS disease.
- `acute`: relaxed chronic-tox thresholds; higher acceptable Cmax.
- `oncology`: hERG and off-target tolerance widened; DepMap selective essentiality preferred over pan-essentiality.

**Tissue of interest** — restricts GTEx / HPA tissue expression scoring to the clinically relevant compartment:

```json
{
  "tissue_of_interest": "string|null (e.g. 'lung', 'liver', 'brain', 'heart')"
}
```

Without this, the system infers tissue from the disease EFO ontology term. Provide explicitly when inference is ambiguous (e.g., systemic autoimmune diseases).

**Seed inputs** — prior knowledge that bypasses scoring thresholds:

```json
{
  "seed_targets": ["GENE1", "GENE2"],
  "seed_smiles": ["SMILES1"],
  "exclude_targets": ["GENE3"],
  "exclude_drugs": ["drugbank:DB12345"]
}
```

- `seed_targets`: gene symbols force-included past Phase 1 aggregate scoring. Use when wet-lab data or strong prior supports a target the pipeline might deprioritize (e.g., low OT association score but validated in your own assay).
- `seed_smiles`: SMILES scaffold(s) to optimize. Pipeline skips de novo generation (Phase 5.1–5.2) and enters directly at Phase 5.6 lead optimization. Use when you have an existing hit series.
- `exclude_targets`: gene symbols hard-excluded from all phases. Use for known clinical failures, liability genes, or targets already covered by a competitor program.
- `exclude_drugs`: DrugBank or ChEMBL IDs excluded from repurposing output. Use when a drug is known to be non-viable for the indication (e.g., already failed Phase II).

**Selectivity constraint** — steers ADMET and docking away from an off-target:

```json
{
  "selectivity_target": "string|null (gene symbol, e.g. 'hERG', 'CYP3A4', 'KCNH2')"
}
```

Used in Phase 5–6 scoring to actively penalize molecules with predicted activity against this target. Distinct from hERG filtering (which is binary pass/fail) — this is a continuous selectivity gradient in the Pareto front.

**Run control**:

```json
{
  "resume_from_phase": "integer|null (1–9, default=null)",
  "dry_run": "boolean (default=false)",
  "output_dir": "string (default='output/{disease_slug}/{timestamp}/')"
}
```

- `resume_from_phase`: skip all phases before this number, reading their cached outputs from `output_dir`. Required for restarting interrupted runs without re-paying compute costs.
- `dry_run`: validates all API credentials, checks local DB file integrity, and prints a projected API call count and cost estimate — but performs no inference. Always run this before a full run.
- `output_dir`: root directory for all phase outputs. Each phase writes `phase{N}_output.json` here; `orchestrate.py` reads this to implement resume logic.

**Human review gates** — the two blocking gates in Phase 1 surface as interactive CLI prompts with a configurable timeout and default:

- Phase 1.1: multiple EFO IDs >0.6 → user selects canonical EFO or confirms merge. Default: highest-scoring EFO, timeout 60s.
- Phase 1.2: 20th target score <0.25 → user confirms proceed with weak signal or aborts. Default: proceed with warning, timeout 30s.

#### 0.3 Database setup checklist (download vs API)

| Resource | Mode | Size | Cost | Notes |
|---|---|---|---|---|
| Open Targets Platform | GraphQL at api.platform.opentargets.org/api/v4/graphql | n/a | Free, no auth | Primary target-disease evidence. Release 24.03 evidence covers 63,226 genes, 25,817 diseases/phenotypes, 17,111 drugs, 7,802,260 target-disease associations |
| Open Targets Genetics | Merged into OT GraphQL | n/a | Free | V2G / L2G scores |
| ChEMBL | REST API + optional SQLite | SQLite ~25 GB | Free | API for queries; download only if doing bulk filtering |
| DrugBank | XML download (requires registration) | 1.5 GB | Free academic / paid commercial | go.drugbank.com/releases |
| PrimeKG | CSV via Harvard Dataverse | edges.csv 368 MB, nodes.csv 7.5 MB | Free | 129,375 nodes / 4,050,249 edges across 20 sources (Chandak et al. 2023) |
| Hetionet v1.0 | JSON download | ~200 MB | Free | het.io/downloads |
| DepMap | CSV bulk + REST | ~2 GB for CRISPR_gene_effect.csv + Gene_Dependency_Profile_Summary.csv | Free | Essential for oncology |
| Pharos / TCRD | GraphQL at pharos-api.ncats.io/graphql | n/a | Free | TDL: Tclin (704 human proteins with approved drugs), Tchem (1,971 proteins with high-potency small-molecule binders), Tbio, Tdark (Sheils et al., Pharos 2023, NAR 51:D1405) |
| DisGeNET | REST (100 q/day free tier) + TSV | 1.2 GB | Free academic | disgenet.com |
| OMIM | API, 1000 req/day free academic | n/a | Free with registration | omim.org/api |
| GWAS Catalog | TSV + REST | ~500 MB | Free | ebi.ac.uk/gwas |
| UniProt | REST + bulk FASTA | human only ~70 MB | Free | rest.uniprot.org |
| STRING | TSV per organism | human 9606 ~2 GB high-conf | Free | string-db.org/cgi/download |
| BioGRID | TAB3 download | ~1 GB | Free academic | thebiogrid.org/download |
| Reactome | GraphQL + GMT | 50 MB GMT | Free | reactome.org/ContentService |
| KEGG | REST (throttled free) | n/a | Free academic, paid commercial | rest.kegg.jp |
| GTEx | REST + bulk TPM | ~3 GB TPM | Free | gtexportal.org/api/v2 |
| Human Protein Atlas | TSV bulk + REST | ~1 GB | Free | proteinatlas.org/about/download |
| AlphaFold DB | per-UniProt PDB/CIF lookup | ~300 KB/file on demand | Free | alphafold.ebi.ac.uk/files/AF-{UNIPROT}-F1-model_v4.pdb |
| AlphaMissense | bulk TSV | 5.5 GB | Free | alphafold.ebi.ac.uk/download |
| LINCS L1000 / CLUE | API at clue.io (registration) | corpus 591,697 profiles, but you use API not full download | Free academic | clue.io/api |
| Enamine REAL | bulk SMILES via Enamine portal (free academic registration) | full set hundreds of GB; the Diverse Drug-Like Set is ~5 GB / ~50M | Free academic | enamine.net/compound-collections/real-compounds |
| ZINC22 | tranche downloads | targeted slices 1-10 GB | Free | zinc20.docking.org / zinc22 |
| PubMed E-utilities | NCBI E-utilities | n/a | Free, 10 req/sec with API key | eutils.ncbi.nlm.nih.gov |
| Europe PMC | REST + GraphQL | n/a | Free | europepmc.org/RestfulWebService |
| Semantic Scholar | Graph API | n/a | Free, 100 req/5min unkeyed, ~1 req/sec with key | api.semanticscholar.org |
| Sci-Hub DOI SQL dump | local SQLite + browser automation | dump ~100 MB metadata, PDFs streamed | User-supplied | Last-resort PDF retrieval |
| PDB | per-structure RCSB REST | individual files | Free | files.rcsb.org |

**Storage budget:** keep ~80 GB free on disk. Mandatory local downloads totaling ~15-20 GB: PrimeKG, DepMap CRISPR matrices, STRING human, GTEx TPM, AlphaMissense human, REAL drug-like slice (~5 GB). Everything else stays as API calls.

#### 0.4 Hosted compute account checklist

| Service | Sign up at | Free offer | Use in pipeline |
|---|---|---|---|
| NVIDIA Build (NIM) | build.nvidia.com | Unlimited free at ~40 RPM (credit system retired early 2025); OpenAI-compatible endpoint | AlphaFold2, OpenFold2, RFdiffusion, ProteinMPNN, DiffDock-V2, MolMIM, GenMol, MSA-Search, ESMFold |
| AlphaFold Server | alphafoldserver.com (Google login) | 30 jobs/day, 5,000 tokens/job | AF3 for protein+ligand+DNA+RNA complexes |
| Neurosnap | neurosnap.ai | Free tier with limited credits | BoltzGen, Boltz-1/2, RFdiffusion2, NeuroFold, DiffDock-L, GNINA, ColabDock, ImmuneBuilder, ProteinMPNN, ADMET-AI, eTox, ToxinPred, GROMACS |
| HuggingFace | huggingface.co | Free Inference API w/ rate limits; Inference Endpoints paid | Backup for ESMFold, ESM-2, ChemBERTa, ADMET-AI |
| Google Colab | colab.research.google.com | Free T4 (limited hrs), Pro $10/mo | Batch protein folding via ColabFold, RFdiffusion smoke tests |
| Modal | modal.com | $30/mo free credit | Per-second billing, MD bursts |
| Replicate | replicate.com | Free T4 tier | Cog-hosted ESMFold, Chai-1, DiffDock |
| RunPod | runpod.io | $5-500 random credit on first $10 spend | Cheapest A100 PCIe 80GB at $1.39/hr (Community Cloud) / A100 SXM 80GB $1.49/hr; H100 PCIe $2.89/hr; H100 SXM $3.29/hr (runpod.io/pricing, May 28, 2026) |
| AWS | aws.amazon.com | 12-mo free tier (orchestration only) | Skip for GPU |
| Anthropic / OpenAI | console.anthropic.com / platform.openai.com | Pay-as-you-go | Literature synthesis LLM |
| Pharos | pharos.nih.gov | Free GraphQL | TDL classification |
| ADMETlab 3.0 | admetlab3.scbdd.com | Free, no registration; programmatic API | Batch ADMET (119 endpoints, >400,000 entries; Fu et al., NAR 52:W422, 2024) |
| SwissADME | swissadme.ch | Free web only | Drug-likeness, BBB, hERG, etc. |

#### 0.5 Local install checklist (one-time)

Ubuntu 22.04 / WSL2 with CUDA 12.x and 6 GB GPU:

```
conda create -n rxdis python=3.10
conda install -c conda-forge rdkit openbabel pdbfixer openmm gromacs networkx scikit-learn pandas pyarrow
pip install requests-cache httpx ratelimit gql[all] biopython pypdb pymol-open-source nglview
pip install reinvent4 admet-ai chembl_webresource_client
pip install autodock-vina
pip install botorch gpytorch
git clone https://github.com/Discngine/fpocket && cd fpocket && make && sudo make install
git clone https://github.com/dauparas/ProteinMPNN
pip install gmx-MMPBSA
pip install boltz
```

**Decision gate Phase 0:** if hosted accounts are not all provisioned, do NOT proceed. **Iteration trigger:** if NIM throughput throttles to under 5 RPM mid-run, batch remaining hosted calls and fall back to Neurosnap and Replicate.

---

### PHASE 1 — Target Identification

#### 1.1 Disease normalization

- **Input:** disease free-text string.
- **Tool:** Open Targets `search` GraphQL (local HTTP).
- **Output:** `{"efo_id":"EFO_xxxxx","name":"...","ontology_terms":[...]}`
- **Decision gate:** if no EFO match >0.6, escalate; try MONDO via mondo.monarchinitiative.org.
- **Edge case (ultra-rare):** use MONDO directly; if empty, OMIM phenotype ID synthetic record.
- **Iteration trigger:** multiple EFOs >0.6 → human picks; pipeline blocks.

#### 1.2 Open Targets target-disease association pull

- **Input:** EFO ID.
- **Tool:** Open Targets GraphQL `disease(efoId).associatedTargets` with all `datatypeScores`, plus `tractability` and `geneticConstraint` per target.
- **Output:** array of:
```json
{"ensembl_id":"ENSG...","approved_symbol":"...","overall_assoc_score":0.0,"datatype_scores":{...},
 "tractability":[{"modality":"SM|AB|PR|OC","label":"...","value":true}],"genetic_constraint":{...}}
```
- **Decision gate:** keep targets with overall_assoc_score > 0.1; cap top 300.
- **Edge case (rare disease):** if <5 targets, drop to 0.05 and merge with DisGeNET hits.
- **Edge case (no targets):** trigger 1.4 (literature) and 1.5 (GWAS) as primary.

#### 1.3 Pharos TDL classification

- **Input:** approved symbols / UniProt IDs from 1.2.
- **Tool:** Pharos GraphQL.
- **Output:** TDL per target ∈ {Tclin, Tchem, Tbio, Tdark}, knowledge availability score.
- **Decision gate:** annotate, do not filter. Flag Tdark for the Phase 2 dark-genome subroutine.
- **Edge case:** if >70% Tdark, set `dark_genome_mode=true`.

#### 1.4 Literature mining

- **Input:** disease string + synonyms.
- **Tools sequentially:**
  1. PubMed E-utilities ESearch + EFetch for disease ANDed with target/biomarker/GWAS/knockout (top 500 abstracts).
  2. Europe PMC `searchPOST` GraphQL; full-text where OA.
  3. Semantic Scholar Graph API `paper/search` + `paper/{id}/references`.
  4. For paywalled critical papers: Playwright against the user's local Sci-Hub DOI SQL dump → fetch PDF; extract with `pypdf`.
- **Synthesis:** chunk to local LLM (Qwen3-4B / Phi-4-mini via Ollama int4 on 6 GB) OR Claude Sonnet via Anthropic API (~$0.50-2 per 500 abstracts) for entity extraction.
- **Output:** `{"gene_symbol":"X","evidence":[{"pmid":"...","sentence":"...","year":2024}],"literature_score":0.0-1.0}`
- **Decision gate:** merge with 1.2, dedupe, aggregate = 0.6·OT + 0.4·literature.
- **Edge case (Sci-Hub miss):** record citation but skip extraction.
- **Iteration trigger:** if median literature score >0.7 for targets NOT in OT list, raise cap from 300 → 500.

#### 1.5 Genetic evidence augmentation

- **Tools (parallel HTTP):** GWAS Catalog REST, OMIM API, DisGeNET REST, OT Genetics L2G/V2G.
- **Output:** per target, `genetic_evidence` block with PMID / p-value / OR / effect size.
- **Decision gate:** any GWAS p<5e-8 with effect>0.1 force-includes target.
- **Edge case (sparse GWAS):** UK Biobank PheWAS via OT Genetics.

#### 1.6 PPI network and centrality

- **Tools:** STRING TSV (conf ≥0.7) + BioGRID TAB3, NetworkX in Python.
- **Computation:** degree, sampled betweenness (200 pivots), closeness, eigenvector. Node2Vec embeddings (`pip install node2vec`) for Phase 2 SHAP. Full human graph ~20K nodes / 1M edges in ~2 GB RAM.
- **Output:** centrality scores per target.
- **Decision gate:** flag targets with eigenvector >95th percentile AND degree >50 as "hub" (attractive but pleiotropic).
- **Edge case:** Tdark targets often absent from STRING → fall back to PrimeKG.

#### 1.7 Pathway and multi-omics

- **Tools:** decoupleR (`decoupler-py`) for pathway/TF activity (MSigDB hallmark, Reactome, PROGENy); gseapy for GSEA; Reactome GraphQL.
- **Output:** per target enriched pathways + NES + p-adj.
- **Decision gate:** boost targets at chokepoints of ≥2 disease-relevant pathways.
- **Edge case (no patient cohort):** TCGA/GTEx via recount3 endpoint or ARCHS4 H5 (~8 GB optional).

#### 1.8 Aggregate scoring → ranked target list

Weights (tunable):
- 0.30 × OT overall_assoc_score
- 0.15 × literature_score
- 0.15 × genetic_evidence_score
- 0.10 × PPI eigenvector centrality (normalized)
- 0.10 × pathway chokepoint score
- 0.10 × tractability_max
- 0.10 × inverse_TDL (Tclin=0.3, Tchem=0.6, Tbio=0.9, Tdark=1.0 — bias toward novelty)

Output:
```json
{"ranked_targets":[{"rank":1,"ensembl_id":"...","symbol":"...","aggregate_score":0.0-1.0,
 "modality_hint":"SM|AB|PR|MG","tdl":"Tchem","evidence_trail":{...}}]}
```

**Decision gate Phase 1:** select top N=20. If 20th score <0.25, warn (weak signal) and consider iterating.

---

### PHASE 2 — Target Validation (in silico)

For each top-N target.

#### 2.1 Essentiality
- **Tools:** DepMap CRISPR_gene_effect.csv lookup (local, pan/selective essentiality via Chronos); ProteomeLM-Ess (Bitbol Lab EPFL, github.com/Bitbol-Lab/ProteomeLM, Apache 2.0; per the bioRxiv 2025.08.01.668221 paper: "we introduce ProteomeLM-Ess, a supervised gene essentiality predictor that generalizes across diverse taxa") — for non-oncology where DepMap is silent. Run via provided Docker on Modal (~$0.10/protein, A10G).
- **Output:**
```json
{"essentiality":{"depmap_chronos_median":-0.X,"depmap_lineages_selective":["..."],
 "proteomelm_ess_score":0.0-1.0,"is_core_essential":true|false}}
```
- **Decision gate:** core_essential AND non-oncology → high-tox flag, -25% aggregate. For oncology, selective essentiality preferred.
- **Edge case (non-cancer):** use ProteomeLM-Ess + OT genetic constraint (LOEUF <0.35 = intolerant to LoF).

#### 2.2 Structure acquisition (routing order)
1. PDB via RCSB REST (≥95% sequence identity).
2. AlphaFold DB at `alphafold.ebi.ac.uk/files/AF-{UNIPROT}-F1-model_v4.pdb` (free, precomputed, instant).
3. ESMFold via NVIDIA NIM or HuggingFace `facebook/esmfold_v1` for novel constructs.
4. AlphaFold Server (AF3, 30/day free) for protein+ligand+DNA+RNA complexes.
5. OmegaFold via Replicate, or Boltz-1 via Neurosnap for ultra-dynamic.
- **Output:** PDB/CIF + pLDDT array.
- **Decision gate:** median pLDDT <70 → route to 2.6 (disordered). Domain pLDDT >80 → use only that domain.
- **Edge case (Tdark no homolog):** ESMFold sequence-only fallback; pLDDT often <60; flag.

#### 2.3 Pocket detection and druggability
- **Tools (ordered):**
  1. fpocket local CPU.
  2. PockDrug-server (browser automation, ~30s/pocket). PockDrug benchmarks (Borrel et al., JCIM 2015, DOI 10.1021/ci5006004): "average accuracy of 87.9% ± 4.7% using a test set"; PockDrug-Server (NAR 43:W436, 2015) reports accuracies >83% (up to 94.6%) depending on pocket estimation method; >20-point MCC improvement vs DoGSiteScorer and fpocket-score on apo sets.
  3. CASTp 3.0 web for cross-check (optional).
  4. Cryptic pockets: cryptosite local OR short 50 ns OpenMM implicit solvent OR hosted P2Rank via Neurosnap.
- **Output:**
```json
{"pockets":[{"id":"P1","volume":350.2,"druggability":0.87,"confidence":0.05,
 "residues":["A123","A156"],"hydrophobicity":0.6,"aromaticity":0.4}]}
```
- **Decision gate:** max druggability <0.5 AND no cryptic → disable SM branch; force biologic/PROTAC.
- **Edge case (membrane):** restrict fpocket to extracellular domain; define boundary via OPM.

#### 2.4 Variant / regulatory effect
- **Tools:** AlphaMissense bulk TSV lookup (local, instant); AlphaGenome via DeepMind preview API (free non-commercial). AlphaGenome performance reference: Avsec et al. Nature 649:1206–1218 (2026, DOI 10.1038/s41586-025-10014-0) reports +14.7% gene expression accuracy and +25.5% eQTL sign prediction over Borzoi, outperforming best external models on 22/24 sequence prediction evaluations and 25/26 variant effect prediction evaluations.
- **Output:** missense pathogenicity + non-coding regulatory impact per locus variant.
- **Decision gate:** multiple AM >0.8 missense segregating with disease → +10% boost.
- **Edge case (synonymous-only / intronic GWAS lead):** AlphaGenome only tractable path; low expression effect → deprioritize.

#### 2.5 PPI validation & off-target
- **Tools:** STRING confidence; ProteomeLM-PPI via Modal (per bioRxiv 2025.08.01.668221: "We further develop ProteomeLM-PPI, a supervised model that combines ProteomeLM embeddings and attention coefficients to achieve state-of-the-art PPI prediction across benchmarks and species"); SwissTargetPrediction once ligand SMILES exists (Phase 5).
- **Output:** PPI partners + confidence; off-target hazard list.

#### 2.6 Disordered / membrane / dark-genome subroutine
- **Trigger:** median pLDDT <70, OR >40% disorder, OR DeepTMHMM positive, OR Tdark.
- **Logic:**
  - Disordered: IUPred3 locally → restrict design to ordered domains; consider PROTAC if any chemistry exists.
  - Membrane: extract ECD only for binder design.
  - Tdark: pull literature corpus + co-expression neighbors from ARCHS4; if zero functional info, flag "very speculative".

#### 2.7 Tissue expression & safety
- **Tools:** GTEx REST + Human Protein Atlas REST (both local HTTP, free).
- **Output:** TSI from HPA, off-tissue expression vector (32 GTEx tissues), critical-tissue flag (heart/brain/kidney TPM >10).
- **Decision gate:** broad expression with high TPM in critical tissues → tox-flag, require selectivity strategy.

#### 2.8 Tractability assessment and modality hint
- **Tool:** local rule engine over OT `tractability` array + 2.1-2.7 outputs.
- **Logic:**
  - SM eligible if: pocket druggability >0.5 AND not heavily disordered AND ChEMBL ≥1 compound activity (target or homolog).
  - AB eligible if: extracellular OR transmembrane with ECD.
  - PROTAC eligible if: intracellular AND any known binder AND E3 accessible.
  - Peptide eligible if: PPI inhibitor use case OR small extracellular target.
  - Oligo eligible if: intracellular AND undruggable AND mRNA detectable.

#### 2.9 Aggregate target validation score with SHAP
- **Tool:** XGBoost classifier per the framework in Alkhadrawi et al. (arXiv 2511.12463, Nov 2025) integrating STRING-derived degree, strength, betweenness, closeness, eigenvector centrality, clustering coefficient + Node2Vec embeddings against DepMap CRISPR essentiality labels; reported AUROC 0.930 / AUPRC 0.656 with GradientSHAP for per-feature attribution.
- **Output:** validation_score 0-1 + SHAP attributions + interpretable evidence trail.
- **Decision gate Phase 2:** select targets with validation_score >0.5 for Phase 3. If <3 pass, lower to 0.3 and warn.

---

### PHASE 3 — Modality Selection Decision Logic

Pure local rule engine.

```
for each target:
  modality_score = {}
  if pocket_druggability > 0.5 AND chembl_has_chemical_matter(target):
    modality_score["SM"] = 0.8*druggability + 0.2*chembl_evidence
  if (intracellular AND has_weak_binder_in_chembl) OR (intracellular AND target_has_E3_proximity):
    modality_score["PROTAC"] = 0.7
  if extracellular OR transmembrane_with_ECD:
    modality_score["AB"] = 0.85
  if PPI_inhibitor_use_case OR target_is_small_extracellular:
    modality_score["peptide"] = 0.75
  if intracellular_undruggable AND mRNA_detectable:
    modality_score["oligo"] = 0.6
  primary = argmax(modality_score)
  secondary = next-highest with score > 0.5
  repurposing_priority = HIGH if approved_drugs_exist OR LINCS_signature_match else LOW
```

Every target enters AT LEAST repurposing (Phase 4) plus primary de novo branch. Secondary branch runs if budget allows.

---

### PHASE 4 — Drug Repurposing Branch

#### 4.1 Approved-drug retrieval
- **Tools (parallel local HTTP):** ChEMBL `target_components`/`mechanisms`, DrugBank XML, Open Targets `knownDrugs`.
- **Output:** approved drugs with ≥weak activity against target or close homolog.
- **Decision gate:** ≥1 approved drug confirms tractability; for new indication, proceed to 4.2.

#### 4.2 LINCS L1000 reverse-signature query
- **Input:** disease signature from patient cohort DE, or public CREEDS/GEO via Enrichr.
- **Tool:** CLUE.io API at clue.io/api (free academic registration). Submit 150-up / 150-down genes against the Touchstone subset (the API queryable subset).
- **Output:** perturbagens with connectivity τ scores (negative = reversal).
- **Decision gate:** keep τ < -90 strong reversal; cross-check DrugBank approval.
- **Edge case:** reproducibility caveat — Lim & Pavlidis 2021 reported only ~17% recall in CMap1→CMap2 self-retrieval; treat LINCS as one of three signals.

#### 4.3 Virtual screening of approved-drug library
- **Input:** target PDB + pocket + approved-drug SMILES library (FDA list ~3K + ChEMBL phase 4 = ~5K unique).
- **Tools:**
  - A. AutoDock Vina local CPU (~10 sec/ligand i7; full library 14 hrs single-threaded, 4 hrs on 4 cores). Receptor prep via prepare_receptor4.py from ADFRsuite.
  - B. Top 200 from Vina → DiffDock-V2 NIM (~$0.005/pose, total <$1).
  - C. Top 50 → Boltz-2 affinity via Neurosnap or local 1B-quantized variant.
- **Output:** ranked with Vina ΔG, DiffDock confidence, Boltz-2 log-µM.
- **Decision gate:** keep Vina < -8.0 AND Boltz-2 log-µM <1.0.
- **Edge case (no hits):** relax to Vina < -7.0; re-examine pocket choice.

#### 4.4 Triangulation
- **Scoring:** repurposing_score = 0.4·docking_norm + 0.35·LINCS_reversal + 0.25·prior_clinical_evidence.
- **Output:** top 10 repurposing candidates per target.
- **Iteration trigger:** zero candidates >0.5 → mark "no obvious repurposing path"; rely on Phase 5/6.

---

### PHASE 5 — De Novo Small Molecule Design

#### 5.1 Pocket-targeted virtual screening (library)
- **Tools:** Enamine REAL Diverse Drug-Like (~5M / ~1 GB on disk). For full 5M, burst to RunPod A100 PCIe 80GB at $1.39/hr Community Cloud (per runpod.io/pricing, May 28, 2026) with QuickVina-W (~$3/full screen). Alternative: DiffDock-V2 NIM "generative-virtual-screening" blueprint against pre-filtered 100K subset.
- **Output:** top 1,000 hits by docking.
- **Decision gate:** Vina ΔG < -8.0 AND RMSD across 3 docking runs <2 Å.

#### 5.2 De novo generation conditioned on pocket
- **Tools (preference order):**
  - REINVENT 4 local with LibInvent/LinkInvent priors + scoring (QED + SA + docking + Boltz-2). Per the MolecularAI/REINVENT4 README: "For most design tasks a memory of about 8 GiB for both CPU main memory and GPU memory is sufficient" — 6 GB will be tight but workable for batches of 100-500.
  - GenMol via NVIDIA NIM (free) fragment-based with scaffold preservation.
  - PocketGen / TamGen via Neurosnap (hosted).
  - DiffSBDD via Replicate.
- **Output:** 5K-10K SMILES with predicted docking.
- **Decision gate:** keep top 1,000 by Pareto front (docking, QED, SA).

#### 5.3 Filtering (all local RDKit)
- PAINS (RDKit FilterCatalog), Lipinski Ro5, Veber, Egan, REOS, SA score (Ertl & Schuffenhauer 2009) or RAscore (Thakkar et al. 2021).
- Novelty: Tanimoto <0.4 vs ChEMBL approved drugs (avoid trivial analogs unless intentional).
- Output: ~200-500 molecules.

#### 5.4 ADMET prediction
- **Tools:** ADMETlab 3.0 API (Fu et al., NAR 52:W422, 2024: "this version includes 119 features, an increase of 31 compared to the previous version. The updated number of entries is 1.5 times larger than the previous version with over 400 000 entries"), free at admetlab3.scbdd.com; SwissADME cross-check; ADMET-AI local CPU (Chemprop-based, minutes).
- **Output:** 30+ endpoints per molecule with confidence.
- **Decision gate:** drop if >2 critical endpoints fail (hERG, AMES, hepatotox, BBB violation if non-CNS).

#### 5.5 Re-dock and rescore
- **Tools:** DiffDock-V2 NIM for top pose; Boltz-2 hosted (Neurosnap) for affinity; AF3 Server for complex prediction with cofactors if budget allows.
- **Decision gate:** top 20 by Boltz-2.

#### 5.6 Lead optimization
- **Tool:** MMP analysis (RDKit) + REINVENT 4 LibInvent / Mol2Mol R-group enumeration; loop through 5.4-5.5.
- **Iteration trigger:** no analog improves >2× affinity AND ADMET → halt; lock parent.

#### 5.7 Edge cases
- Undruggable pocket → redirect to Phase 6 (peptide) or PROTAC.
- All molecules fail ADMET → restart 5.2 with scaffold seed from ChEMBL.
- No MD-stable pose → drop; next target.

---

### PHASE 6 — De Novo Biologic / Peptide Design

#### 6.1 Backbone generation (hosted-only on this hardware)
- **Primary: BoltzGen via Neurosnap.** Stark et al. (bioRxiv 2025.11.20.689494): "We introduce BoltzGen, an all-atom generative model for designing proteins and peptides across all modalities to bind a wide range of biomolecular targets." MIT licensed (github.com/HannesStark/boltzgen). Submit target + binder length range (30-120 aa mini-binders; 8-30 peptides) + Cyclic flag.
- **Alternative: RFdiffusion NIM.** Per NIM docs (docs.nvidia.com/nim/bionemo/rfdiffusion): "The RFdiffusion NIM requires NVIDIA GPUs with at least 12 GB of GPU Memory" and "compute capability >7.0" + "at least 15GB of free hard drive space". Hosted-only on a 6 GB RTX 3050.
- **Not recommended on this hardware: BindCraft.** Per BindCraft README: "However, as the pipeline requires significant amount of GPU memory to run for larger target+binder complexes, we highly recommend to run it using a local installation and at least 32 Gb of GPU memory" — use only if paying Neurosnap or renting A100 on RunPod ($1.39-$1.49/hr).
- **Output:** N (50-200) backbone PDBs.

#### 6.2 Sequence design
- ProteinMPNN local (github.com/dauparas/ProteinMPNN) on 6 GB for binders <150 aa; OR ProteinMPNN via NIM for larger.
- 8 sequences/backbone typically.

#### 6.3 Refolding validation
- AlphaFold2 NIM with `initial_guess` for binder-target complex (free credits); Boltz-2 (Neurosnap) for harder cases; AF3 Server for ligand/cofactor complexes.
- **Decision gate:** ipTM >0.7 AND pAE_interface <10 Å AND binder pLDDT >80.
- **Edge case (low ipTM cluster):** widen RFdiffusion sampling OR shift hotspots.

#### 6.4 Peptide-specific design (8-30 aa)
- ProtFlow (Kong et al., arXiv 2504.10983, Apr 2025): "we introduce ProtFlow, a fast flow matching-based protein sequence design framework that operates on embeddings derived from semantically meaningful latent space of protein language models" — no widely-published public code repo as of May 2026; route to Neurosnap if exposed, otherwise BoltzGen substitute.
- HelixGAN for helical mini-binders via Neurosnap if exposed.
- Cyclic peptides: AfCycDesign / HALLUCINATE cyclic mode via Neurosnap.
- **Decision gate:** cyclize if intracellular target (proteolytic stability).

#### 6.5 Developability
- Aggregation: CamSol web, Aggrescan3D (via Neurosnap), TANGO local CLI.
- Solubility: NetSolP-1.0 via Neurosnap.
- Immunogenicity: NetMHCpan 4.1 local (free academic) for MHC-I/II 9-mer/15-mer binding; threshold 500 nM strong.
- Humanization: SAbPred Humaneness OPIG webserver; V-gene identity against human germline IGHV.
- Stability: DeepSTABp or Boltz-2 thermostability fine-tuned heads.
- **Decision gate:** no aggregation hotspot >median, solubility >0.6, <5 strong MHC binders.

#### 6.6 Edge cases
- Backbone unpredictable / low ipTM across all → peptide route.
- Aggregation flag on all → introduce surface charge, break hydrophobic patch, re-MPNN.
- Immunogenic for all designs in chronic non-cancer indication → disqualifying; flag for de-immunization (out of scope).

---

### PHASE 7 — Multi-Parameter Lead Optimization (MPO)

#### 7.1 Desirability function
- BoTorch (local 6 GB GPU comfortably) Gaussian process over potency, selectivity, ADMET, novelty, developability, SA.
- Output: Pareto front + scalar.

#### 7.2 Active-learning loop
- qNEHVI acquisition for multi-objective.
- 3-5 iterations: suggest 20 candidates (REINVENT 4 biased by GP for SM; mutations on top backbones for biologics) → evaluate (5.4-5.5 or 6.3-6.5) → update GP → re-rank.
- Stop: Pareto hypervolume improvement <1% OR 100 evaluated OR budget exhausted.

---

### PHASE 8 — In-Silico Validation Gate

#### 8.1 Short MD pose stability
- **Tools:** GROMACS local on RTX 3050. Practitioner benchmark (ResearchGate 2023): 47,500-atom protein-ligand system at 2 fs on RTX 3050 with WSL2 gives ~14 ns/day, vs ~100 ns in 30-40 min on RTX 3080 Ti. A 10 ns sanity per pose ≈ 17 hours — run only top 5-10 candidates.
- OpenMM more memory-efficient alternative for 10-50 ns.
- Burst MD: GROMACS containers on RunPod RTX 4090 / A100 ($1.39/hr A100 PCIe); SaladCloud GROMACS benchmark (2024) shows consumer GPUs deliver ~90% of datacenter MD performance at <10% of cost.
- **Decision gate:** drop if ligand RMSD >3 Å sustained >30% of trajectory.

#### 8.2 Binding free energy refinement
- **Tools:**
  - gmx_MMPBSA locally: single-trajectory MM-GBSA on 10 ns trajectory, ~30 min/ligand on 6 GB.
  - Top 3 candidates: relative FEP via PMX (open source) hosted on Modal A100 (~$2-5 per perturbation pair).
  - For absolute FEP, Boltz-ABFE pipeline (Recursion/MIT) hosted on Neurosnap — per Bio-IT World (Oct 2025): "Boltz-2 dropped the cost from approximately $100 per prediction that took 6-12 hours to just a few cents for a 20-second prediction on a single GPU."
- **Decision gate:** ΔG < -8 kcal/mol (~µM Ki) for SM; ipTM >0.8 for biologics in lieu of FEP.

#### 8.3 Final scorecard

```json
{
  "target_validation_score": 0.0-1.0,
  "candidate_score": 0.0-1.0,
  "combined_score": 0.0-1.0,
  "subscores": {
    "binding_affinity": ..., "pose_stability": ..., "admet_or_developability": ...,
    "selectivity": ..., "novelty": ..., "tractability_modality_alignment": ...
  },
  "evidence_trail": {...}
}
```

Default weights: 0.30 binding + 0.20 stability + 0.20 ADMET/developability + 0.15 selectivity + 0.10 novelty + 0.05 modality_alignment.

---

### PHASE 9 — Output Packaging

```
output/
├── run_metadata.json         (disease, EFO, timestamp, DB versions, model commits)
├── ranked_targets.json
├── targets/
│   └── {gene_symbol}/
│       ├── target_validation.json
│       ├── structure.pdb
│       ├── pockets.json
│       ├── candidates_repurposing.json
│       ├── candidates_de_novo_sm.json
│       ├── candidates_biologic.json
│       ├── poses/{candidate_id}_pose.pdb + _md_summary.json
│       └── admet/{candidate_id}_admet.json
├── citations.bib
├── compute_log.json          (per-step cost, time, hosted vs local)
└── README.md
```

**Reproducibility:** pin DB versions (OT release tag, ChEMBL version, AFDB v4, PrimeKG release), pin model versions (Boltz-2 commit, REINVENT 4 version), persist exact GraphQL queries. Include Dockerfile and environment.yml.

---

## End-to-End Worked Example: Idiopathic Pulmonary Fibrosis (IPF)

**Phase 0 input:** `disease_name="idiopathic pulmonary fibrosis"`, modality_preference="any", budget=$25.

**Phase 1 output (top 5):**
1. *TGFB1* — OT 0.78, GWAS p=3e-12, literature 0.91, eigenvector 99th, TDL Tchem, SM+AB+peptide tractable, aggregate 0.79.
2. *MUC5B* — OT 0.71, rs35705950 risk variant well-established, TDL Tbio, aggregate 0.66.
3. *IL11* — OT 0.65, anti-IL11 antibody in trials, Tchem, AB-preferred, aggregate 0.64.
4. *LOXL2* — OT 0.55, simtuzumab phase II failure adds caution, Tchem, aggregate 0.55.
5. *ROCK1* — OT 0.51, TDL Tclin (fasudil), high repurposing potential, aggregate 0.62.

**Phase 2 (TGFB1):**
- Structure: AlphaFold DB AF-P01137-F1; median pLDDT 88.
- Pockets: P1 druggability 0.71, P2 (TGFBR1 interface) 0.66.
- Essentiality: not core (Chronos -0.2); LOEUF 0.42.
- AlphaMissense: 14 high-pathogenicity missense in disease cohort.
- Modality eligibility: {SM:0.7, AB:0.85, peptide:0.75}; primary=AB, secondary=peptide.

**Phase 3:** TGFB1 → Phase 4 repurposing + Phase 6 biologic/peptide.

**Phase 4 (TGFB1):**
- Approved drugs: galunisertib (TGFBR1, phase II), fresolimumab (clinical), ~150 ChEMBL compounds.
- LINCS reversal: pirfenidone (already approved IPF — mechanistic confirmation), nintedanib (also approved), unexpected baricitinib τ=-95.
- FDA library docking: niclosamide (Vina -9.5, Boltz-2 log-µM 0.3), itraconazole (-9.1, 0.4), digoxin (-8.7, 0.6).
- Combined: niclosamide and itraconazole flagged (literature already supports antifibrotic effect — credibility boost).

**Phase 6 (TGFB1 peptide branch):**
- BoltzGen via Neurosnap, 100 designs, 16-aa cyclic peptides targeting TGFB1-TGFBR1 interface.
- Refolding: 23 designs ipTM>0.75; developability: 11 pass aggregation+solubility+immunogenicity.
- Top 3 ranked by Boltz-2.

**Phase 8 (top 3 SM + top 3 peptide):**
- MD: niclosamide RMSD 1.2 Å avg over 10 ns; itraconazole drifts (3.5 Å) — drop. Top peptide P1 ipTM=0.82.
- MM-GBSA: niclosamide ΔG=-9.8 kcal/mol; P1 Boltz-ABFE ≈ -10 kcal/mol equivalent.

**Phase 9:** (TGFB1, niclosamide) high-confidence repurposing; (TGFB1, P1-cyclic-peptide) novel biologic; (IL11, tocilizumab analog) already in development, deprioritize; (ROCK1, fasudil expansion) fast-follower repurposing.

**Compute spend:** ~$8.20 (NIM ~$0, Neurosnap BoltzGen ~$4, RunPod A100 4 hrs MD ~$5.56 at $1.39/hr). Wall-clock: ~36 hours including human review gates.

---

## Compute Budget Table

| Phase / Step | Hosted vs Local | Per-step cost |
|---|---|---|
| 0 Setup downloads | Local | Free |
| 1.2 Open Targets | Local HTTP | Free |
| 1.3 Pharos | Local HTTP | Free |
| 1.4 Literature mining (500 abstracts, Claude synthesis) | Local + Anthropic API | <$1 |
| 1.5 GWAS / OMIM / DisGeNET | Local HTTP | Free |
| 1.6 PPI NetworkX | Local | Free |
| 1.7 decoupleR / GSEA | Local | Free |
| 1.8 Aggregate scoring | Local | Free |
| 2.1 DepMap + ProteomeLM-Ess | Local + Modal ($0.10/target) | <$1 (20 targets) |
| 2.2 Structure | Local + NIM | Free |
| 2.3 fpocket + PockDrug | Local + browser | Free |
| 2.4 AlphaMissense + AlphaGenome | Local + DeepMind preview | Free |
| 2.5 ProteomeLM-PPI | Modal | <$1 |
| 2.6 Disorder/membrane subroutine | Local | Free |
| 2.7 GTEx / HPA | Local HTTP | Free |
| 2.8 Tractability rules | Local | Free |
| 2.9 SHAP scoring | Local | Free |
| 4.1 Approved-drug retrieval | Local HTTP | Free |
| 4.2 LINCS L1000 | Local HTTP (clue.io) | Free |
| 4.3 Vina library screen | Local CPU | Free (time) |
| 4.3 DiffDock-V2 rescore top-200 | NIM | <$1 |
| 4.3 Boltz-2 top-50 | Neurosnap | <$10 |
| 5.1 Library docking 5M | RunPod A100 PCIe burst at $1.39/hr | <$10 |
| 5.2 REINVENT 4 / GenMol | Local + NIM | Free to <$1 |
| 5.3 Filters | Local | Free |
| 5.4 ADMETlab 3.0 | Web/API | Free |
| 5.5 DiffDock + Boltz-2 rescoring | NIM + Neurosnap | <$10 |
| 5.6 MMP optimization | Local | Free |
| 6.1 BoltzGen 100 designs | Neurosnap | <$10 |
| 6.1 RFdiffusion fallback | NIM | Free |
| 6.2 ProteinMPNN | Local or NIM | Free |
| 6.3 AF2 NIM refolding | NIM | Free |
| 6.4 ProtFlow / HelixGAN | Neurosnap | <$10 |
| 6.5 Developability | Local + Neurosnap | <$1 |
| 7 BoTorch | Local | Free |
| 8.1 MD top-10 local | Local | Free (time) |
| 8.1 MD bursts A100 | RunPod $1.39-$1.49/hr | <$10 |
| 8.2 gmx_MMPBSA | Local | Free |
| 8.2 PMX FEP top-3 | Modal | <$10 |
| 8.2 Boltz-ABFE top-3 | Neurosnap | <$10 |
| 9 Packaging | Local | Free |
| **Total (typical disease, 5 targets through Phase 8)** | | **$30-80** |

---

## Consolidated Tool & Resource Registry

| Name | Type | URL | Access | Where |
|---|---|---|---|---|
| Open Targets Platform | DB/API | platform.opentargets.org | Free, GraphQL | 1.2, 2.8 |
| Open Targets Genetics | DB/API | genetics.opentargets.org | Free, GraphQL | 1.5 |
| Pharos / TCRD | DB/API | pharos.nih.gov, pharos-api.ncats.io/graphql | Free | 1.3 |
| DisGeNET | DB/API | disgenet.com | Free academic | 1.5 |
| OMIM | DB/API | omim.org/api | Free w/ key | 1.5 |
| GWAS Catalog | DB/API | ebi.ac.uk/gwas/rest | Free | 1.5 |
| ChEMBL | DB/API | ebi.ac.uk/chembl | Free | 4.1, 5.1 |
| DrugBank | DB | go.drugbank.com | Free academic | 4.1 |
| PrimeKG | KG | github.com/mims-harvard/PrimeKG | Free | 1.4, 4.4 |
| Hetionet | KG | het.io | Free | 1.4 backup |
| DepMap | DB | depmap.org/portal | Free | 2.1 |
| STRING | DB | string-db.org | Free | 1.6, 2.5 |
| BioGRID | DB | thebiogrid.org | Free academic | 1.6 |
| Reactome | DB/API | reactome.org | Free | 1.7 |
| KEGG | DB/API | kegg.jp | Free academic | 1.7 |
| UniProt | DB/API | uniprot.org | Free | 2.2 |
| GTEx | DB/API | gtexportal.org | Free | 2.7 |
| Human Protein Atlas | DB/API | proteinatlas.org | Free | 2.7 |
| AlphaFold DB | DB | alphafold.ebi.ac.uk | Free | 2.2 |
| AlphaFold Server (AF3) | Hosted | alphafoldserver.com | 30/day free | 2.2, 6.3 |
| AlphaMissense | DB | alphafold.ebi.ac.uk/download | Free | 2.4 |
| AlphaGenome | Hosted preview | deepmind.google | Free non-commercial | 2.4 |
| LINCS / CMap | DB/API | clue.io | Free academic | 4.2 |
| Enamine REAL | DB | enamine.net | Free academic | 5.1 |
| ZINC22 | DB | zinc20.docking.org | Free | 5.1 |
| PubMed E-utils | API | eutils.ncbi.nlm.nih.gov | Free | 1.4 |
| Europe PMC | API | europepmc.org | Free | 1.4 |
| Semantic Scholar | API | api.semanticscholar.org | Free | 1.4 |
| NVIDIA NIM | Hosted | build.nvidia.com | Unlimited free at ~40 RPM | 2.2, 5.2, 5.5, 6.1, 6.2 |
| Neurosnap | Hosted | neurosnap.ai | Free + paid | 2.3, 4.3, 5.2, 5.5, 6.1-6.5, 8.2 |
| HuggingFace Inference | Hosted | huggingface.co | Free + paid | 2.2, 5.4 |
| Modal | Hosted | modal.com | $30/mo free credit | 2.1, 8.2 |
| RunPod | Hosted | runpod.io | A100 PCIe 80GB $1.39/hr Community Cloud | 5.1, 8.1 |
| Replicate | Hosted | replicate.com | Pay per use | 2.2, 5.2 |
| Google Colab | Hosted | colab.research.google.com | Free T4 / Pro $10/mo | Backup folding |
| RDKit | Library | rdkit.org | Free | 5.3 |
| AutoDock Vina | Tool | vina.scripps.edu | Free, local | 4.3, 5.1 |
| fpocket | Tool | github.com/Discngine/fpocket | Free, local | 2.3 |
| PockDrug-server | Web | pockdrug.rpbs.univ-paris-diderot.fr | Free, browser | 2.3 |
| CASTp | Web | sts.bioe.uic.edu/castp | Free, browser | 2.3 |
| REINVENT 4 | Tool | github.com/MolecularAI/REINVENT4 | Free, local (~8 GiB GPU) | 5.2, 5.6 |
| ADMETlab 3.0 | Web/API | admetlab3.scbdd.com | Free | 5.4 |
| SwissADME | Web | swissadme.ch | Free | 5.4 |
| ADMET-AI | Local | github.com/swansonk14/admet_ai | Free | 5.4 |
| Boltz-2 | Tool/hosted | github.com/jwohlwend/boltz; Neurosnap | Free + hosted | 4.3, 5.5, 8.2 |
| BoltzGen | Tool/hosted | github.com/HannesStark/boltzgen; Neurosnap | Free MIT + hosted | 6.1 |
| DiffDock-V2 | NIM | build.nvidia.com/nvidia/diffdock | Free | 4.3, 5.5 |
| RFdiffusion | NIM | docs.nvidia.com/nim/bionemo/rfdiffusion | Free (12 GB GPU min hosted) | 6.1 |
| ProteinMPNN | Tool | github.com/dauparas/ProteinMPNN | Free, local | 6.2 |
| BindCraft | Tool | github.com/martinpacesa/BindCraft | Free but ≥32 GB GPU recommended | 6.1 fallback only |
| ProteomeLM | Tool | github.com/Bitbol-Lab/ProteomeLM | Free Apache 2.0 | 2.1, 2.5 |
| ProtFlow | Paper | arxiv.org/abs/2504.10983 | Paper only; no public repo confirmed | 6.4 |
| MolGene-E | Paper | pmc.ncbi.nlm.nih.gov/articles/PMC11888154 | Paper only | 4 advisory |
| GROMACS | Tool | gromacs.org | Free, local | 8.1, 8.2 |
| OpenMM | Tool | openmm.org | Free, local | 8.1 |
| gmx_MMPBSA | Tool | github.com/Valdes-Tresanco-MS/gmx_MMPBSA | Free, local | 8.2 |
| PMX FEP | Tool | github.com/deGrootLab/pmx | Free; hosted recommended | 8.2 |
| NetworkX | Library | networkx.org | Free, local | 1.6 |
| decoupleR | Library | github.com/saezlab/decoupler-py | Free, local | 1.7 |
| BoTorch | Library | botorch.org | Free, local | 7 |
| NetMHCpan | Tool | services.healthtech.dtu.dk/services/NetMHCpan-4.1 | Free academic | 6.5 |
| Sci-Hub DOI dump | User-supplied | local SQLite | User + browser automation | 1.4 fallback |

---

## Failure Modes and Recovery

| Failure | Phase | Recovery |
|---|---|---|
| No EFO match | 0/1 | Try MONDO, OMIM phenotype ID; abort with diagnostic if still empty |
| Open Targets returns 0 associated targets | 1.2 | Fall back to literature mining (1.4) + GWAS (1.5) as primary |
| Disease rare, <50 PubMed hits | 1.4 | Reduce literature filter strength; Semantic Scholar related-paper expansion; rely on GWAS |
| NVIDIA NIM throttled mid-run | 2.2, 5, 6 | Switch to Neurosnap; then HuggingFace Inference; last resort, batch-defer |
| AlphaFold Server 30/day cap hit | 2.2, 6.3 | ESMFold via NIM for non-complex; queue and resume next day for AF3-required |
| Structure pLDDT <70 throughout | 2.2 → 2.6 | Treat as disordered; restrict to short ordered fragments; consider PROTAC |
| All pockets fail druggability | 2.3 | Disable SM branch; force peptide/biologic (6) and/or PROTAC |
| BindCraft GPU OOM | 6.1 | Switch to BoltzGen (Neurosnap) or RFdiffusion NIM |
| All BoltzGen ipTM <0.7 | 6.3 | Wider backbone diversity, alternative hotspots; if persistent, target may be poor PPI candidate |
| MD diverges on RTX 3050 | 8.1 | Reduce timestep to 1 fs; shorten to 5 ns; burst to RunPod A100 |
| gmx_MMPBSA fails on charged ligand | 8.2 | Linear PB instead of nonlinear; or switch to Boltz-ABFE hosted |
| Final scorecard zero candidates >0.5 | 9 | Loop back to Phase 5/6 with relaxed generation; broader Pareto |

---

## Recommendations

**Staged build order for Claude Code:**

1. **Stage 1 — Phase 0 + Phase 1 only (Week 1-2):** scaffold the DB access layer; get Open Targets + Pharos + literature mining + PPI centrality + aggregate scoring end-to-end. Output ranked target JSON. *Acceptance:* feed "pancreatic cancer", get top-20 with KRAS, TP53, CDKN2A, SMAD4 in top 10. *Trigger to advance:* top-5 overlap with published target lists ≥3/5 across 3 test diseases (oncology, autoimmune, neurodegenerative).
2. **Stage 2 — Phase 2 + Phase 3 (Week 3-4):** structure routing, pocket detection, modality decision. *Acceptance:* for KRAS G12C, system correctly identifies cryptic switch-II pocket and recommends covalent SM. *Trigger:* correct modality on 5/7 benchmark targets.
3. **Stage 3 — Phase 4 (Week 5):** repurposing standalone. Validate against known successes (e.g., baricitinib for COVID-19 via LINCS). *Trigger:* known approved-drug pairs reproduced for ≥3 targets.
4. **Stage 4 — Phase 5 (Week 6-7):** small molecule de novo. Validate by re-generating known inhibitors of well-studied targets. *Trigger:* ≥1 generated molecule with Tanimoto >0.6 to a known approved drug.
5. **Stage 5 — Phase 6 (Week 8):** biologic/peptide de novo. Heavy hosted reliance (BoltzGen primarily). *Trigger:* ipTM >0.7 on a benchmark like PD-L1.
6. **Stage 6 — Phase 7 + 8 (Week 9-10):** MPO loop, MD, FEP. *Trigger:* binding-ranking reproducibility across two independent runs.
7. **Stage 7 — Phase 9 + reproducibility (Week 11):** packaging, citations, Dockerfile.

**Stop / escalation thresholds during a run:**
- Hosted spend >50% of budget before Phase 5 → pause and review.
- Phase 2 produces zero validated targets → abort and revisit Phase 1 thresholds.
- Phase 8 produces zero candidates passing for any target → abort that target, proceed to next.

**Iteration policy:** at most 2 outer iterations (relax thresholds → re-run from Phase 1.8 or 2.9). After 2 failed iterations the disease genuinely has no tractable in-silico path with current methods; the answer is "no candidates, here are the failure modes."

**Marginal money first:** (1) Neurosnap Standard plan if doing biologics, (2) RunPod A100 hours for FEP and large library docking, (3) Anthropic API for literature synthesis. Skip Colab Pro unless >20 jobs/day on free quota; skip AWS GPU entirely (worse $/hr than RunPod for this workload).

---

## Caveats

1. **Boltz-2 affinity is a ranking signal, not absolute truth.** The known systematic deviations in ring planarity, chirality, and saturation states (independent evaluations published 2025-2026) mean Boltz-2 should always be paired with at least one orthogonal score (Vina, GNINA, MM-GBSA) before greenlighting.
2. **AlphaFold Server access policy has been a moving target.** 10/day at May 2024 launch → 20/day after May 2024 community backlash → 30/day as of January 2026 (Bonvin Lab tutorial). Plan for tighter limits if Google reduces quota. Always have ESMFold as fallback.
3. **The pipeline assumes English-language literature.** Semantic Scholar, Europe PMC, PubMed skew anglophone. For diseases primarily studied in Chinese, Japanese, German literature, supplement with CNKI / J-STAGE / OPAC.
4. **LINCS L1000 cell-line coverage is biased toward common cancer lines.** For non-oncology, reverse-signature matching is much weaker. CMap1→CMap2 self-retrieval recall was only ~17% per Lim & Pavlidis 2021.
5. **BindCraft is the highest-quality binder design tool currently published, but its ≥32 GB GPU requirement means it never runs natively here.** For BindCraft-quality on 6 GB, rent A100 on RunPod or pay Neurosnap. BoltzGen and RFdiffusion NIM are the next best alternatives and are explicitly hosted-friendly.
6. **MolGene-E and ProtFlow are research-stage with limited or no public code release as of May 2026.** Treat as advisory references; substitute well-supported tools (LINCS direct query; BoltzGen for peptide) until repos appear.
7. **ProteomeLM is recent (Aug 2025 bioRxiv / late 2025 PNAS).** Adoption is early; cross-validate essentiality calls against DepMap for any oncology target.
8. **Tdark targets are tagged with high uncertainty throughout.** A Tdark target reaching final output should be flagged "speculative" — historical hit rates are roughly 20-30% vs ~60-70% for Tchem.
9. **Wet-lab validation is explicitly out of scope.** Even the best in-silico candidate has historical cellular-assay hit rates of 20-50% for biologics, lower for small molecules. The output is a prioritized hypothesis list, not a clinical lead list.
10. **All hosted services can change pricing, deprecate models, or impose new rate limits without notice.** The pipeline must include health-check probes at Phase 0 that detect deprecated endpoints and re-route. NVIDIA NIM has shown model deprecations (Kimi K2 Instruct, GLM-4.7, Gemma 3 27B all carried deprecation notices in early 2026). Re-run Phase 0 0.4 verification before any new disease run.