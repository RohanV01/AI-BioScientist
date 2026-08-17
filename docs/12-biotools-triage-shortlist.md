# bio.tools + GitHub Repo Triage Shortlist

Full triage of the Vault's `Computational-Biology/` catalog (19 categories, ~33,888 bio.tools entries + the 1,000-repo GitHub Topic Index), done 2026-08-16 per explicit user directive: go through every tool, not just star-ranked/language-filtered subsets. 13 parallel subagents, each reading every row of its assigned category's file in full (confirmed per-agent, no sampling). Supersedes the earlier narrower pass over just Cheminformatics + Immunoinformatics.

**Status markers used below:**
- `[ ]` not yet built
- `[x]` built and live-verified (see `10-build-plan.md` for the commit)

**Integration path legend:** PIP = installable Python package, wrap in-process (the pattern used for scikit-bio/BioPandas/cobra/RDKit+Vina). CLONE = needs source cloned into the repo and run/imported directly (no clean pip package). DATA = real capability but needs a dataset (FASTQ/BAM/VCF/scRNA-seq matrix/etc.) a chat agent doesn't have on hand — defer until there's an actual data-ingestion story. GPU = deep learning model needing GPU/large weights — Phase 6 territory, not now. UNCLEAR = summary alone wasn't enough to tell.

Already-built tools (16 external-API + scikit-bio, BioPandas, cobra, Vina/RDKit/Meeko, Hugging Face) are NOT relisted here — see `10-build-plan.md` Phase 3/5.

---

## Structural biology / docking (extends the existing Vina/PDB/AlphaFold tools)

- [ ] **Fpocket** (CLONE, High) — binding-pocket/cavity detection from a static PDB structure. Lets Vina docking work on apo structures without a co-crystallized reference ligand.
- [ ] **US-align** (CLONE, High) — universal structural alignment / TM-score / RMSD across proteins, nucleic acids, complexes. Real structure-comparison gap.
- [ ] **DockQ** (PIP, Medium) / **spyrmsd** (PIP, Medium) — score docking pose quality/RMSD; complements Vina output.
- [ ] **Foldseek** (CLONE, High) / **FoldMason** (CLONE, Medium) — structure-vs-structure similarity search; multi-structure alignment.
- [ ] **DSSP** (CLONE, High) — secondary structure assignment from a PDB file.
- [ ] **PLIP** (PIP, High) — non-covalent interaction profiling (H-bonds, π-stacking, etc.) from a protein-ligand complex; explains a Vina docking pose.
- [ ] **IDPConformerGenerator** (PIP, High) — 3D conformer ensembles for intrinsically disordered protein regions from sequence.
- [ ] **correlationplus** (PIP, Medium-High) — dynamical/allosteric residue correlation from a static structure (Elastic Network Model, no trajectory needed).
- [ ] **HADDOCK3** (CLONE, Medium) — protein-protein/protein-nucleic-acid docking (Vina only does small-molecule).
- GPU-later: DiffDock, RFdiffusion, ProteinMPNN, OpenFold, ProtGPT2, DiffDock-PP, FlowDock, FABind, PoseBench (benchmark, not a tool).

## Sequence analysis fundamentals (currently zero coverage)

- [ ] **BLAST+** (CLONE, High) — sequence similarity search, the single most fundamental missing operation.
- [ ] **DIAMOND** (CLONE, High) — BLAST-class results at much larger scale.
- [ ] **HMMER3 / pyhmmer** (PIP, High) — profile-HMM / remote homology / Pfam-domain search.
- [ ] **Clustal Omega** (CLONE, High) / **MAFFT** (CLONE, High) — multiple sequence alignment.
- [ ] **EMBOSS** (CLONE, High) — pairwise alignment (needle/water), primer picking, sequence composition/ORF utilities.
- [ ] **Minimap2 / mappy** (PIP, High) — versatile pairwise aligner (long reads, cDNA, genome-vs-genome).
- [ ] **Prodigal** (CLONE, High) — ab initio prokaryotic gene prediction from a genome sequence, no external DB needed.
- [ ] **MUMmer4** (CLONE, High) — whole-genome-to-genome alignment/synteny.
- [ ] **Primer3 / primer3-py** (PIP, High) — PCR/qPCR primer design.
- DATA-gated (need FASTQ/BAM/VCF): BWA, GATK, FreeBayes, RepeatMasker, DeepVariant, kallisto.

## Phylogenetics (currently zero coverage)

- [ ] **IQ-TREE** (CLONE, High) / **FastTree** (CLONE, High) — ML phylogenetic tree inference from an alignment.
- [x] **ete3** (skipped, used DendroPy instead) / **DendroPy** (PIP, High) — programmatic tree construction/manipulation/comparison.
- [x] **piqtree** (PIP, High) — Python-native IQ-TREE bindings, no shelling out.
- [ ] **PhyKIT** (PIP, High) / **BioKIT** (PIP, Medium-High) — one-command tree/alignment statistics.
- [ ] **OrthoFinder** (CLONE, High) — ortholog/orthogroup inference across genomes.
- [ ] **PAML** (CLONE, Medium-High) — dN/dS selection testing.
- [ ] **ASTRAL-Pro2** (CLONE, Medium-High) — coalescent species-tree estimation from gene trees.

## Transcriptomics / scRNA-seq (currently zero coverage — largest single gap found)

- [ ] **SCANPY** (PIP, High) — the field-standard Python scRNA-seq toolkit (QC, clustering, trajectory, DE).
- [ ] **GSEApy** (PIP, High) — gene set enrichment analysis (GSEA/ORA) from a gene list.
- [ ] **g:Profiler / gprofiler-official** (PIP, High) — gene-list functional enrichment + ID conversion, REST-backed.
- [ ] **Enrichr (via gseapy)** (PIP, High) — enrichment against 30+ gene-set libraries, simple REST wrapper.
- [ ] **clusterProfiler** (CLONE, R, High) — GO/KEGG enrichment + GSEA.
- [ ] **pyComBat** (PIP, High) — batch-effect correction.
- [ ] **scVelo** (PIP, High) — RNA velocity (cell-state transition dynamics).
- [ ] **rMATS** (CLONE, High) — differential alternative splicing.
- [ ] **WGCNA / PyWGCNA** (CLONE/PIP, High) — weighted gene co-expression network analysis.
- [ ] **SCENIC** (CLONE, High) — gene regulatory network inference from scRNA-seq.
- [ ] **VIPER** (CLONE, High) — regulon-based protein/TF activity inference from expression.
- [ ] **HunFlair (flair)** (PIP, High) — biomedical named entity recognition from free text; could auto-tag entities in PubMed/OpenAlex results.
- [ ] **OmniPath** (PIP, High) — integrated signaling pathways + ligand-receptor cell communication (distinct from STRING/KEGG/Reactome).
- [ ] **BUSCO** (PIP, Medium) — genome/transcriptome/proteome assembly completeness scoring.
- Many more strong R/Bioconductor candidates (Seurat, scran, scater, SoupX, monocle, InferCNV, Giotto, TCGAbiolinks, recount3, tximport, sleuth, etc.) — see full agent transcripts; deferred as a group because they need an **R subprocess/rpy2 bridge**, a new architectural piece none of the Python tools needed.
- DATA-gated: most cell-type-annotation and deconvolution tools need a real expression matrix (celltypist, MACA, Scaden, xCell2, etc.) — worth building once there's a real data-ingestion story (e.g. a GEOquery/recount3 tool that fetches one).

## Population genetics (strong, clean-input-shape yield)

- [ ] **pixy** (PIP, High) — nucleotide diversity (π) / divergence (dxy) from a VCF.
- [ ] **poolfstat** (CLONE, High) — Fst from allele-count data.
- [ ] **egglib** (PIP, High) — general pop-gen stats engine (diversity, Fst, Tajima's D).
- [ ] **msprime** (PIP, High) — coalescent simulation from demographic parameters.
- [ ] **ADMIXTURE** (CLONE, High) / **Eigensoft** (CLONE, High) — ancestry/population-structure inference.
- [ ] **TreeMix** (CLONE, High) — population tree + admixture edges from allele frequencies.
- [ ] **selscan** (CLONE, High) — haplotype-based selection-scan statistics (iHS, XP-EHH).
- [ ] **LDSC** (CLONE, High) — SNP heritability + genetic correlation from GWAS summary stats.
- [ ] **pandasGWAS** (PIP, Medium-High) — query the GWAS Catalog programmatically.

## Metagenomics / microbiology (large, well-organized yield)

- [ ] **sourmash** (PIP, High) — MinHash genome/metagenome comparison, lightweight.
- [ ] **Kraken2** (CLONE, High) / **Kaiju** (CLONE, Medium) — taxonomic classification of sequences/reads.
- [ ] **MetaPhlAn** (CLONE/PIP, High) / **HUMAnN** (CLONE/PIP, Medium) — taxonomic/functional profiling directly from real shotgun metagenomic FASTQ.
- [ ] **Prokka** (CLONE, High) / **Bakta** (CLONE, High) — bacterial genome annotation.
- [ ] **AMRFinderPlus** (CLONE, High) — antimicrobial resistance gene/mutation detection.
- [ ] **CheckM2** (CLONE/PIP, High) / **CheckV** (CLONE, Medium-High) — genome/MAG completeness+contamination QC.
- [ ] **eggNOG-mapper** (PIP, High) — functional annotation (GO/KEGG/COG) from sequence.
- [ ] **FastANI** (CLONE, High) — whole-genome Average Nucleotide Identity.
- [ ] **GTDB-Tk** (CLONE, High, heavy DB) — standardized genome taxonomy assignment.
- [ ] **dada2** (CLONE, R, High) — amplicon sequence variant (ASV) calling from 16S/ITS FASTQ.
- [ ] **Barrnap** (CLONE, High) — rRNA gene prediction, lightweight.

## Cheminformatics / drug discovery (extends ChEMBL + Vina)

- [ ] **pyscreener** (PIP, High) — batch virtual screening orchestration (many compounds × Vina).
- [ ] **LightDock** (PIP, High) — protein-protein docking.
- [ ] **Auto3D** (PIP, Medium-High) — SMILES → 3D conformers (fills the gap between ChEMBL's 2D SMILES and Vina's need for 3D structures).
- [ ] **AiZynthFinder** (PIP, High) — retrosynthetic route planning.
- [ ] **Chemprop** (PIP, High) — trainable/pretrained molecular property prediction (MPNN).
- [ ] **eQuilibrator** (PIP, High) — reaction/compound Gibbs free energy; pairs with cobrapy FBA.
- [ ] **SolTranNet** (PIP, High) — aqueous solubility from SMILES.
- [ ] **BioTransformer** (CLONE, High) / **Pickaxe** (PIP, High) — metabolite/biotransformation prediction from a structure.
- [ ] **RAscore** (CLONE, Medium) — synthesizability scoring.
- [ ] **ToxinPred2** (CLONE, Medium) — peptide/protein toxicity prediction.
- [ ] **xtb** (CLONE, Medium) — fast semi-empirical QM geometry/energy calculations.
- [ ] **libRoadRunner** (PIP, High) / **basico** (PIP, Medium) — SBML kinetic/ODE model simulation (dynamic, complements cobrapy's steady-state FBA).
- [ ] **straindesign** (PIP, Medium) — metabolic engineering intervention design, built on cobrapy.

## Immunoinformatics

- [ ] **MHCflurry** (PIP, High) — peptide-MHC-I binding affinity prediction.
- [ ] **epitopepredict** (PIP, High) — unified T-cell epitope prediction framework.
- [ ] **ANARCI** (PIP, High) — antibody/TCR sequence numbering (Kabat/Chothia/IMGT).
- [ ] **AbLang** (PIP, High) — antibody sequence language model.
- [ ] **BioPhi** (PIP, High) — antibody humanization + humanness scoring.
- [ ] **PyIR** (PIP, High) — antibody/TCR V(D)J gene assignment (IgBLAST wrapper).
- [ ] **clusTCR** (PIP, Medium) / **tcrdist3** (PIP, Medium) — TCR repertoire clustering/distance.

## Proteomics (mass spec — currently zero coverage)

- [ ] **mokapot** (PIP, High) — pure-Python PSM rescoring for FDR control.
- [ ] **Pyteomics** (PIP, High) — foundational MS file-format parsing (mzML, MGF, pepXML) — prerequisite plumbing for the rest of this cluster.
- [ ] **Comet** (CLONE, High) / **Sage** (CLONE, Medium) — MS/MS database search engines.
- [ ] **DIA-NN** (CLONE, High) — modern DIA proteomics search+quant.

## Synthetic biology (small category, zero coverage, genuinely good yield)

- [ ] **bebop/poly** (CLONE, High) — DNA sequence engineering (codon optimization, primers, part assembly).
- [ ] **OpenCloning** (PIP/API, High) — cloning/genome-engineering strategy design with a documented API.
- [ ] **PEGG** (PIP, High) — prime-editing pegRNA design.
- [ ] **nrpcalc** (PIP, Medium-High) — non-repetitive DNA part design.

## Other notable finds

- [ ] **cptac** (PIP, Medium) — CPTAC proteogenomic (mutation+CNV+transcriptomics+proteomics per tumor sample) data access.
- [ ] **pyBioPortal** (PIP, Medium-High) — cBioPortal cancer genomics REST client.
- [ ] **DDGun** (CLONE, Medium) — protein stability change (ΔΔG) from a point mutation; pairs with ClinVar.
- Noted but not pursued: **ahmedanees-m/bio-firewall** — a biosecurity-hazard screen for AI-agent-generated genome-editing plans. Thematically relevant to this very platform (1 star, unproven) — worth a look later, not now.

---

## What was deliberately excluded (all categories)

- Pure database/web-portal entries with no downloadable code or API.
- "Awesome list" curated-link aggregators, course-list repos, dataset/benchmark collections.
- Near-duplicate tools once one strong representative was picked per capability cluster (noted per-agent in the full transcripts).
- Anything requiring raw sequencing reads (FASTQ/BAM), a scRNA-seq count matrix, an MD trajectory file, or another real dataset a chat session doesn't have on hand — tagged DATA above, not dropped, since a future data-ingestion tool could unlock the whole cluster at once.
- GPU-heavy deep learning models (DiffDock, RFdiffusion, OpenFold, ChromBPNet, etc.) — real capabilities, explicitly deferred to Phase 6's compute-layer decision, not this pass.

## Architectural note: R/Bioconductor

A large fraction of the strongest transcriptomics/epigenetics/population-genetics candidates (Seurat, scran, DESeq2-adjacent, WGCNA's original R form, dada2, ADMIXTURE-adjacent R wrappers, etc.) are R packages, not Python. Every tool built so far in this platform is pure Python (in-process import) or a Python-wrapped CLI binary. Wiring R tools needs either an `rpy2` bridge or subprocess calls to `Rscript` — a genuinely new piece of infrastructure, not just "another pip install." Worth deciding deliberately before building the first R-based tool, rather than defaulting into it.
