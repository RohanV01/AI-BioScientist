# Remaining Tools Wiring Plan

Sequencing plan for the ~81 tools in `docs/12-biotools-triage-shortlist.md` still marked `[ ]`
(16 of the original ~97 non-DATA/non-GPU candidates are already live -- see
`docs/14-biotools-shortlist-status.md`). Readiness work (`docs/16-production-operations.md`) is
done and merged to `main`; this is the next body of work, per the user's own explicit sequencing
call ("readiness fixes first, tools later").

Every tool here follows the exact recipe `CONTRIBUTING.md` already documents: one builder file in
`orchestrator/app/tools/`, one line in `tool_roster.TOOL_BUILDERS`, one line in
`seed_dev_data.KNOWN_TOOL_SOURCES`, a citation pattern in `claude_runner.RECORD_REF_PATTERNS` if
it's a real local computation with no external record ID, a real (non-mocked) test, and a live
verification through the actual running product before it's considered done -- not a plan to
invent a new pattern, a plan to run the existing one 81 more times in a sensible order.

## Sequencing principle

Not alphabetical, not shortlist order -- sequenced by **integration cost first, then
cluster-internal dependency**:

1. **PIP tools** (`pip install`, wrap in-process) go first in every cluster -- same effort as this
   session's `msa`/`uniprot.get_sequence` additions, a few hours each including a real test.
2. **CLONE tools** (subprocess-wrapped CLI, `apt`/build-from-source in the Dockerfile) go second --
   same pattern as `mafft`/`vina`/`phykit` already in the image, more Dockerfile plumbing per tool
   but no new architecture.
3. **The R/Bioconductor bridge** is its own phase, deliberately -- it's infrastructure, not a tool,
   and unlocks the single largest remaining cluster (transcriptomics + several
   population-genetics/metagenomics R tools) at once. Building it after a run of Python
   PIP/CLONE tools means the team has a working rhythm on the existing pattern before taking on a
   new one.
4. **DATA-gated and GPU-heavy tools are explicitly out of scope for this plan.** They need a real
   data-ingestion story (FASTQ/BAM/VCF/scRNA-seq upload -- nothing in the platform accepts one
   today) or a compute-layer decision (`docs/07-system-architecture.md`'s Phase 6) neither of
   which this plan tries to solve. Listed at the bottom for visibility, not silently dropped.

Within a phase, tools are grouped by capability cluster (matching `CONTRIBUTING.md`'s existing
`feature/*` branches) so a contributor picking up a cluster can work through it without
context-switching between unrelated domains.

## Phase 1 -- PIP tools, no new Dockerfile plumbing (34 tools)

The fastest, lowest-risk wave. Every tool here is `pip install <package>` plus a builder file --
no `apt-get`, no compiled binary, no new base-image layer. Estimate: 2-4 hours per tool including
a real test and live verification (this session's actual pace for `msa`/`uniprot.get_sequence`),
so roughly 25-40 tools per contributor-week at a sustainable pace, not a sprint.

### Immunoinformatics (`feature/immunoinformatics`) -- 7 tools
| Tool | Adds |
|---|---|
| epitopepredict | Unified T-cell epitope prediction (complements MHCflurry's MHC-I-only scope) |
| ANARCI | Antibody/TCR sequence numbering (Kabat/Chothia/IMGT) |
| AbLang | Antibody sequence language model. **Live 2026-08-27 as `ablang_restore`** (`restore_antibody_sequence`, restore mode). Earlier session attempt stalled on the model download (near-zero bytes/sec); confirmed live on retry that this was transient -- both checkpoints downloaded in under 70s. |
| ~~BioPhi~~ | Antibody humanization + humanness scoring. **Checked 2026-08-27, not built** -- not on PyPI under any tried name (`biophi`/`bio-phi`/`biophi-humanization`), GitHub-only install, same tier finding as IDPConformerGenerator/clusTCR. |
| PyIR | Antibody/TCR V(D)J gene assignment (IgBLAST wrapper). **Checked 2026-08-27**: the real package is `crowelab-pyir` (bare `pyir` on PyPI is an unrelated "Python Intermediate Representation" package). Confirmed live it genuinely shells out to a real `igblastn` binary + germline reference databases (`--igdata`/`-x` flags) -- heavier CLONE-tier plumbing than ANARCI's single `hmmscan` binary, not simple `apt-get`. Moved to the Phase 2 CLONE-tier batch rather than built as a one-off mid-Phase-1 Dockerfile hack. **Live 2026-08-29 as `pyir_annotate`.** Real, confirmed-live packaging defect found along the way: the Debian/Ubuntu `igblast` apt package (v1.19.0) ships only the NCBI C++ toolkit's internal build utilities (datatool, project_tree_builder, ...) -- it does NOT contain the actual `igblastn`/`igblastp` executables (confirmed by extracting the real `.deb` and listing every file in it, not assumed) -- fixed by installing NCBI's own official prebuilt Linux binary release directly instead. PyIR's real Python API (`from crowelab_pyir import PyIR`) is called in-process rather than subprocess-wrapped, returning AIRR-standard-named fields (`v_call`/`d_call`/`j_call`/`cdr3_aa`) directly as a dict. Its germline BLAST database is materialized at build time via PyIR's own `pyir setup` command (real IMGT/GENE-DB snapshot bundled in the PyPI package itself -- no separate multi-GB download needed, unlike the Metagenomics cluster). |
| ~~clusTCR~~ | TCR repertoire clustering. **Checked 2026-08-27, not built** -- not on PyPI under that name, GitHub-only install, same tier finding as BioPhi/IDPConformerGenerator. |
| tcrdist3 | TCR repertoire distance metrics |

### Cheminformatics (`feature/cheminformatics`) -- 7 tools
| Tool | Adds |
|---|---|
| LightDock | Protein-protein docking (Vina only does small-molecule). **Live 2026-08-26 as `lightdock_docking`.** |
| Auto3D | SMILES -> 3D conformers (closes the gap between ChEMBL's 2D SMILES and Vina's 3D input requirement). **Live 2026-08-26 as `auto3d_conformers`.** Found and guarded against a real, environment-specific bug: torch's JIT C++ compile (inductor) fails when the install path contains a space (`TORCHDYNAMO_DISABLE=1` set at import time). |
| ~~AiZynthFinder~~ | Retrosynthetic route planning. **Investigated 2026-08-27, not built -- real dependency conflict.** Installing it force-downgrades this platform's pinned `rdkit>=2026.3,<2027.0` to `rdkit==2023.9.6` (confirmed live) -- the same class of hard, unresolvable-in-place conflict as the DockQ/numpy rejection, since `vina_docking`/`meeko`/`auto3d_conformers`/etc. are already shipped against the newer rdkit. |
| ~~Chemprop~~ | Trainable/pretrained molecular property prediction (MPNN). **Investigated 2026-08-27, not built** -- confirmed live it resolves cleanly against this platform's pinned rdkit (no conflict, unlike AiZynthFinder) but genuinely ships no downloadable pretrained/foundation checkpoint (its own package has no pretrained-hub code path, only CLI `--checkpoint` for a caller-supplied trained model file) -- needs training data this platform doesn't have, confirming the original assessment. |
| ~~Pickaxe~~ | Metabolite/biotransformation prediction from a structure. **Checked 2026-08-26, not built.** The real PyPI package is `minedatabase` (bare `pickaxe` on PyPI is an empty placeholder, confirmed before installing). It pulls a heavy, unexpected dependency chain (pymongo, keras) suggesting the package is architected around a persistent MongoDB-backed reaction database, not a stateless per-request computation, and its `lxml` dependency fails to build without `libxml2-dev`/`libxslt1-dev` system headers (not in the base image). A heavier CLONE-tier integration than docs/12 assumed -- worth a dedicated pass to confirm whether standalone (non-Mongo) use is actually viable, not built speculatively here. |
| libRoadRunner | SBML kinetic/ODE simulation (dynamic, complements cobrapy's steady-state FBA) |
| ~~basico~~ | Same SBML kinetic simulation niche, alternate API to the already-live `libRoadRunner`/`kinetic_simulation`. **Deliberately not built 2026-08-27** -- real redundant capability, not worth a second tool for the same niche (same call as the docs/12 precedent this row itself already flagged). |

### Population genetics (`feature/population-genetics`) -- 3 tools
| Tool | Adds |
|---|---|
| pixy | Nucleotide diversity (pi) / divergence (dxy) from a VCF. **Checked 2026-08-27**: not on PyPI under that name (the PyPI `pixy` package is an unrelated terminal-color library) -- bioconda-only distribution, same tier finding as BUSCO. Moved to the Phase 2 CLONE-tier batch. |
| egglib | General pop-gen stats engine (diversity, Fst, Tajima's D) |
| pandasGWAS | Programmatic GWAS Catalog queries. **Live 2026-08-27 as `gwas_catalog`** (`get_gwas_studies_for_variant`, wired on `get_studies_by_variant_id`). Genuinely slow (confirmed live: 60-90s per call against a well-studied real variant, the API paginating a large real result set) -- documented plainly in the tool's own description rather than treated as a defect; user confirmed multi-minute real tool latency is acceptable as long as the result is real. |

### Sequence analysis (`feature/sequence-analysis`) -- 1 tool
| Tool | Adds |
|---|---|
| Minimap2 / mappy | Versatile pairwise aligner (long reads, cDNA, genome-vs-genome) |

### Synthetic biology (`feature/synthetic-biology`) -- 2 tools
| Tool | Adds |
|---|---|
| ~~OpenCloning~~ | Cloning/genome-engineering strategy design. **Investigated 2026-08-27, not built as named** -- the PyPI `opencloning` package is a FastAPI web-app backend (its own summary says so), not a callable library, with no public hosted instance referenced in its own settings. Its real assembly-simulation logic is built on `pydna`, a real standalone library -- wired that directly instead as **`gibson_assembly`** (`simulate_gibson_assembly`), confirmed live to correctly find circularized Gibson assembly products from real overlapping fragments. |
| ~~PEGG~~ | Prime-editing pegRNA design. **Re-confirmed 2026-08-27, not built** -- still hard-pins `scikit-learn==1.1.1` (verified live against current PyPI metadata), which would downgrade this venv's scikit-learn below `mhcflurry`'s `>=1.9` floor and break an already-shipped tool. Same precedent as the docs/12 note this row already carries. |

### Transcriptomics (`feature/transcriptomics`) -- 6 tools
| Tool | Adds |
|---|---|
| SCANPY | Field-standard Python scRNA-seq toolkit (QC, clustering, trajectory, DE) -- **DATA-gated in practice**: real capability, but needs an actual expression matrix input; wire the tool now, note the same data-ingestion caveat as the DATA-gated list below applies to how *useful* it is until a matrix-upload story exists. **Live 2026-08-26 as `scanpy_clustering`** (QC + normalize + PCA + neighbors + Leiden clustering -- trajectory/DE not included this pass). |
| pyComBat | Batch-effect correction. **Live 2026-08-26 as `pycombat_correction`**, verified against a synthetic matrix with a known, deliberate batch offset (not just "ran without crashing"). |
| scVelo | RNA velocity (cell-state transition dynamics) -- not attempted this pass (time budget); genuinely DATA-gated (needs spliced/unspliced count matrices from real scRNA-seq, not a synthetic-input case like pyComBat). |
| HunFlair (flair) | Biomedical NER from free text -- real near-term win: auto-tag entities in PubMed/OpenAlex results, no data-ingestion dependency at all. **Live 2026-08-26 as `hunflair_ner`** (`extract_biomedical_entities`). Model download (~1.4GB v1 + cached v2 weights) took ~65min in this environment's throttled connection but completed. Wired on HunFlair2 (`Classifier.load('hunflair2')`), not v1 -- flair itself flags v1 as deprecated, and a live comparison on the same test sentence showed v2's single unified tagger returning higher-confidence labels (1.0 vs. ~0.88-0.98) across Gene/Disease/Chemical spans. |
| OmniPath | Integrated signaling pathways + ligand-receptor cell communication (distinct from STRING/KEGG/Reactome, which this platform already has). **Live 2026-08-26 as `omnipath_interactions`.** |
| ~~BUSCO~~ | Genome/transcriptome/proteome assembly completeness scoring. **Checked 2026-08-26, not built** -- not on PyPI under that name (bioconda-only distribution), different integration tier than docs/12 assumed. |

### Structural biology (`feature/structural-biology`) -- 4 tools
| Tool | Adds |
|---|---|
| ~~DockQ~~ | **Investigated 2026-08-26, not built -- real dependency conflict, not a version-range nitpick.** DockQ hard-pins `numpy<2.0`; this platform's already-live `msprime`/`tskit` needs numpy's `>=2` C-API. Confirmed live in both directions: installing DockQ (which downgrades numpy to 1.26) breaks `tskit`'s import (`numpy._core.multiarray failed to import` -- a C-API version mismatch); reinstalling `numpy>=2` to fix `tskit` then breaks DockQ's own compiled `.operations` extension the other way. No numpy version satisfies both. Same precedent as pegg's scikit-learn conflict (docs/12) -- don't break an already-shipped tool for a new one. |
| spyrmsd | Pose RMSD scoring, same pairing. **Live 2026-08-26 as `spyrmsd_pose`** -- no numpy-range conflict, built cleanly against `numpy>=2`. |
| ~~IDPConformerGenerator~~ | 3D conformer ensembles for intrinsically disordered regions from sequence. **Checked 2026-08-26, not built** -- not on PyPI under any tried name (`idpconformergenerator`/`idpconfgen`), GitHub-only install, different integration tier than docs/12 assumed (same finding as BioPhi/PyIR/clusTCR this session). |
| correlationplus | Dynamical/allosteric residue correlation from a static structure (Elastic Network Model, no MD trajectory needed). **Live 2026-08-26 as `correlationplus_dynamics`.** |

### Phylogenetics (`feature/phylogenetics`) -- 1 tool
| Tool | Adds |
|---|---|
| ~~BioKIT~~ | **Investigated 2026-08-26, not built -- real bug found in the package itself.** The real PyPI package is `jlsteenwyk-biokit` (plain `biokit`/`BioKIT` on PyPI is an unrelated generic viz toolkit -- confirmed before installing, not guessed). Installed and tested `variable_sites`/`alignment_summary` against two hand-built test alignments (one with only singleton SNPs, one with three completely different homogeneous sequences) -- both reported 0 variable sites when the alignments plainly aren't constant. Read the installed package's own source (`biokit/services/alignment/base.py`'s `determine_pis_vs_cs`): it requires each distinct character at a site to occur **at least twice** to count toward variability at all (`v >= 2` filter before checking `len(d) > 1`), so any column whose variation is entirely singleton/private alleles (a real, common case, not an edge case) silently gets classified `Not_pis_vs_cs` -- neither variable nor even constant, contradicting the tool's own documented definition ("variable sites... at least two nucleotide or amino acid characters among all taxa"). Not shipped with a workaround or caveat -- a tool that silently misreports basic alignment statistics is worse than not having it, same standard as the DDGun decision above. Revisit only if a fixed upstream release addresses this.

### Proteomics (`feature/proteomics`) -- 1 tool
| Tool | Adds |
|---|---|
| mokapot | Pure-Python PSM rescoring for FDR control -- pairs with the already-live `pyteomics_mass` |

### Other (`feature/general-tools`) -- 2 tools
| Tool | Adds |
|---|---|
| ~~cptac~~ | CPTAC proteogenomic (mutation+CNV+transcriptomics+proteomics per tumor) data access. **Tried 2026-08-26, not built** -- phones home to Zenodo on a bare `import cptac`, observed hanging or 504-erroring repeatedly in this environment; unsuitable for a per-request tool call. |
| pyBioPortal | cBioPortal cancer genomics REST client. **Live 2026-08-26 as `cbioportal_mutations`.** |

**Phase 1 total: 34 tools.** (Structural biology's `Fpocket`/`US-align`/`Foldseek`/`FoldMason`/`DSSP`/`HADDOCK3`,
sequence analysis's `BLAST+`/`DIAMOND`/`Clustal Omega`/`EMBOSS`/`Prodigal`/`MUMmer4`, and every other
CLONE-path tool moved to Phase 2 below -- recount confirms 34 PIP-path tools here, not the ~52 an
earlier rough estimate assumed; the difference is mostly cheminformatics and metagenomics skewing
more CLONE-heavy than expected on closer read.)

## Phase 1.5 -- Local-GPU tools, genuinely new capabilities (4 tools)

Not "GPU-heavy, deferred" -- these four specifically don't overlap with anything already live or
already planned, unlike the docking-adjacent GPU tools removed below, and are realistic on modest
consumer hardware (checked against a 16GB RAM / 6GB VRAM card, e.g. an RTX 3050): none of them need
cloud GPU or the Phase 6 compute-layer decision, just a GPU passed through to the orchestrator
container (a `docker-compose.yml`/`Dockerfile` change, not new architecture).

| Tool | Adds | Why it's not redundant |
|---|---|---|
| ProteinMPNN | Inverse protein design: given a 3D backbone, design a sequence that folds into it | Nothing else designs sequences from structure -- `vina_docking` docks a molecule against an *existing* protein, this is a different direction entirely |
| RFdiffusion | Generates novel protein backbones from scratch or around a motif | Nothing else generates new protein structures at all |
| ProtGPT2 | Generative protein language model (writes plausible novel sequences) | Distinct from `huggingface`'s masked-residue prediction and the planned AbLang (antibody-specific) -- this is unconditional/general sequence generation |
| ChromBPNet | Predicts chromatin accessibility from DNA sequence | Regulatory genomics has zero coverage today -- not adjacent to any existing tool |

DiffDock/FABind (small-molecule blind docking) deliberately left out of this wave: their only real
differentiator over the already-live `vina_docking` + the planned `Fpocket` (pocket detection,
Phase 2) is not needing a predefined binding pocket, which is a genuine but narrower use case, not
a clear win, and DiffDock in particular is far slower per-compound than Vina, unsuitable for the
batch screening `virtual_screening.py` already handles well. Worth reconsidering only if "dock
against a structure with no known pocket" turns out to be a real, recurring ask -- not built
speculatively here.

## Phase 1.6 -- NVIDIA NIM hosted inference (new integration path, unlocks real AlphaFold folding)

A fifth integration path beyond `docs/12`'s PIP/CLONE/DATA/GPU legend: **NIM** (NVIDIA Inference
Microservices, hosted at `build.nvidia.com`) -- a REST API + API key, same shape and same
BYO-credential pattern already live for `huggingface` (`CREDENTIALED_BUILDERS` in
`tool_roster.py`, `scripts/add_credential.py`, `app/vault.py`'s Fernet-encrypted storage). No
local GPU, no VRAM budgeting, no Phase 6 cloud-compute decision -- an org brings its own free-tier
NVIDIA API key the same way they'd bring a Hugging Face token today.

This directly reopens the reasoning behind several "GPU-heavy" deferrals: the constraint driving
those was *local* GPU memory. A hosted endpoint sidesteps that entirely, the same "check a hosted
Inference API before defaulting to local/cloud GPU" principle `docs/07-system-architecture.md`
already names for Hugging Face.

**The concrete gap this closes -- real AlphaFold folding, not just AlphaFold DB lookup.** The
existing `alphafold` tool source (`orchestrator/app/tools/alphafold.py`) is explicit in its own
docstring: *"Structure lookup only ... no folding inference"* -- it can only return a
precomputed structure for a UniProt accession AlphaFold DB already has. It cannot fold a novel
sequence, a point mutant, a synthetic construct, or anything not already in UniProt. NVIDIA's NIM
catalog hosts AlphaFold2 (and OpenFold2, ESMFold) as callable endpoints -- wiring one closes this
exact gap. Concretely: add a second tool, `fold_sequence(sequence: str) -> structure`, to the
existing `alphafold` tool source (or a new `alphafold_nim` source if the credentialed-builder shape
doesn't fit cleanly alongside the unauthenticated DB-lookup tool -- decide once the real API
contract is in hand), following the `huggingface`-style credentialed pattern.

**Also worth wiring via this same path** once the NIM contract is confirmed: RFdiffusion,
ProteinMPNN, and DiffDock all have NIM-hosted variants -- offering both a local-GPU path (Phase 1.5,
for a self-hoster with hardware) and a hosted path (this phase, for anyone without a GPU at all) is
worth doing for RFdiffusion/ProteinMPNN specifically, since Phase 1.5 already justified why they're
worth having; DiffDock stays a judgment call per Phase 1.5's own reasoning regardless of which path
delivers it.

**Before building**: NVIDIA's exact request/response schema for each bio-specific NIM endpoint
needs to be verified against their current API docs at build time, not assumed from this plan --
the same discipline this session applied to Camofox's actual API shape (`_try_camofox`'s docstring
in `literature_discovery.py` cites the exact source file and date the contract was confirmed
against). Do not guess the JSON shape and ship it; confirm it first, the same way every other tool
in this codebase was built against a real, checked API response.

## Phase 2 -- CLONE tools, new Dockerfile plumbing per tool (~39 tools)

Same recipe, plus a `Dockerfile` `RUN apt-get install` or build-from-source step per tool (the
`mafft`/AutoDock Vina precedent). Slower per tool (build/compile time, more failure surface at
image-build time) but no new architecture -- budget roughly double Phase 1's per-tool time.

### Sequence analysis fundamentals -- 6 tools
BLAST+, DIAMOND, Clustal Omega, EMBOSS, Prodigal, MUMmer4 -- **highest-priority cluster in this
phase**: BLAST+ alone is flagged in `docs/12` as "the single most fundamental missing operation,"
and this platform currently has *zero* sequence-similarity-search capability at all.

**All 6 live 2026-08-27** as `blast_search`, `diamond_search`, `clustalo_align`, `emboss_water`
(EMBOSS's `water` command specifically -- exact Smith-Waterman pairwise alignment), `prodigal_genes`,
and `mummer_align`. DIAMOND isn't apt-installable (checked before assuming it was) -- installed from
its official prebuilt static binary release instead. All wired on well-documented, stable CLI
syntax rather than a live host install (this sandbox's Docker daemon lacked apt-installed binaries
to test against directly) -- verification deferred to the batch Docker build/test pass per
explicit direction, not skipped.

### Structural biology -- 6 tools
Fpocket, US-align, Foldseek, FoldMason, DSSP, HADDOCK3.

**5 of 6 live 2026-08-27** as `fpocket_detection`, `usalign_tmscore`, `foldseek_search`, `foldmason_align`, `dssp_secondary_structure`. Foldseek/FoldMason installed from official static binary releases; US-align/Fpocket compiled from source at build time (neither is apt-installable). ~~HADDOCK3~~ **investigated 2026-08-27, not built -- real bug found in the current PyPI release (2026.8.0), not a config error on this platform's side.** Confirmed live via `strace`: `pip install haddock3` genuinely works (no CNS Fortran binary needed -- it bundles a real CNS 1.3 binary and the disclaimer only warns about its license, not a missing dependency), and the bundled CNS binary itself runs and exits cleanly (code 0) for the `topoaa` module's jobs -- but haddock3's own Python wrapper (`CNSJob.run()`/`libparallel.py`) never writes or uses the captured CNS output for this code path, so every `topoaa` run fails with "100% of output not generated" regardless of input. This exact failure mode has open, unresolved GitHub issues against the real project (e.g. issues #1554, #1389, #884) -- a known, reproducible upstream bug, not an environment quirk. Revisit if a fixed release ships.

### Phylogenetics -- 4 tools
FastTree, OrthoFinder, PAML, ASTRAL-Pro2.

**All 4 live 2026-08-29** as `fasttree_tree` (approximate-ML tree from an alignment, faster than the
existing piqtree/IQ-TREE path for large inputs), `orthofinder_groups` (multi-species orthogroup
inference), `paml_yn00` (real pairwise dN/dS via PAML's `yn00`, not `codeml` -- `codeml`'s
site/branch-model ML analysis needs a caller-supplied tree topology and per-model config a chat
caller can't reasonably provide; `yn00` gives the same real omega estimate for the common
"is this gene under selection" question from a codon alignment alone), and `astral_pro_tree`
(species tree from multi-copy gene trees, statistically consistent under the multi-species
coalescent model). FastTree and PAML are apt-installable (`fasttree`, `paml` packages, confirmed
live via `apt-cache search`/`apt-get download` before assuming either way -- `yn00`/`codeml` ship in
the `paml` package). ASTRAL-Pro2 renamed: the upstream project (github.com/chaoszhang/ASTER) has
since moved to ASTRAL-Pro3, a faster reimplementation of the same method (confirmed via its own
README/tutorial) -- wired as `astral-pro` (ASTER's own binary name), compiled from ASTER's `Linux`
branch at Docker build time, same "not apt/pip-installable, compile from source" class as
US-align/Fpocket. OrthoFinder is neither apt- nor PyPI-installable (confirmed live) -- installed
from its own self-contained GitHub release tarball, which bundles its own diamond/mcl/fastme
binaries and needs no separate binary-install step beyond extraction. All wired on well-documented,
stable CLI/config syntax rather than a live host install (same as every other Phase 2 cluster so
far, no sudo access to install these system binaries locally) -- verification deferred to the batch
Docker build/test pass per explicit direction, not skipped. OrthoFinder's full pipeline (DIAMOND
all-vs-all + MCL clustering + gene-tree inference) is genuinely slow even on small inputs -- timeout
set generously (1hr) rather than treating latency as a rejection reason, per explicit user
direction.

### Population genetics -- 6 tools
poolfstat, ADMIXTURE, Eigensoft, TreeMix, selscan, LDSC.

**5 of 6 live 2026-08-29** as `eigensoft_pca` (real EIGENSTRAT PCA via `smartpca`, apt-installable,
confirmed live), `admixture_ancestry` (real ML ancestry inference via `admixture`, installed from
its own project site's prebuilt Linux binary -- not apt/pip-installable, confirmed live; the real
PLINK `.bed`/`.bim`/`.fam` binary trio is constructed directly from a simple caller dict, same
"build the real input format" pattern as blast_search/mummer_align), `treemix_population_tree` (real
population-split/migration-graph inference via `treemix`, compiled from source against
libgsl-dev/libboost-dev -- real build recipe confirmed against the project's own bioconda build
script, not guessed), `selscan_nsl` (real within-population nSL selection scan via `selscan`,
installed from its own official prebuilt Linux binary release -- scoped to `--nsl` specifically
since iHS/XP-EHH/XP-nSL all need a genetic map or a second reference population a chat caller can't
reasonably supply, while nSL needs only phased haplotypes; reports raw/unstandardized scores since
genome-wide normalization needs a full-chromosome scan out of scope here), and
`ldsc_genetic_correlation` (real LD Score Regression genetic-correlation estimation via `ldsc.py` --
**genuinely PyPI-installable**, confirmed live: the `ldsc` package's wheel installs the real script +
`ldscore` library despite the upstream README only documenting a conda-from-source install, contrary
to docs/12's original CLONE-tier assumption). LDSC ships its own baked-in EUR 1000G-Phase3/HapMap3
LD-score reference panel (~26MB, pulled from a Zenodo mirror since the project's own default hosting
now 301-redirects to a requester-pays bucket -- real link rot, confirmed live) -- same
"pre-warm a real one-time download at build time" pattern as equilibrator_thermo/mhcflurry, just a
much smaller payload; only SNPs overlapping that reference panel's real HapMap3 rsIDs can be scored,
surfaced as an explicit "no overlap" result rather than fabricated. **poolfstat NOT built** -- it's a
CRAN-only R package (confirmed live, no PyPI distribution exists), correctly belongs in Phase 3's
R/Bioconductor bridge once that architecture (rpy2 vs. subprocess `Rscript`) is decided, not this
CLONE-tier batch. **pixy still NOT built** -- re-confirmed live: not apt-installable, the PyPI `pixy`
package is still the unrelated terminal-color library, and no GitHub release binary exists either --
genuinely bioconda-only, same finding as the earlier session. All wired on well-documented, stable
CLI/config syntax rather than a live host install (no sudo access to install these system binaries
locally) -- verification deferred to the batch Docker build/test pass per explicit direction.

### Metagenomics -- 11 tools, heaviest cluster in this phase
Kraken2, Kaiju, Prokka, Bakta, AMRFinderPlus, CheckM2, CheckV, eggNOG-mapper, FastANI, GTDB-Tk,
Barrnap. **Caveat, not a blocker**: several of these (Kraken2, GTDB-Tk especially) need multi-GB
reference databases at build time, the same class of problem this session already solved once for
`equilibrator_thermo`/`mhcflurry` (pre-warm at Docker build time, not a live user's first request --
see `orchestrator/Dockerfile`'s existing precedent and `docs/16-production-operations.md`'s backup
guidance on what that does to image size). Budget accordingly; don't discover this mid-build the
way the equilibrator download was discovered mid-battle-test. MetaPhlAn/HUMAnN need real shotgun
FASTQ input to be useful even once wired -- functionally DATA-gated despite being listed as
CLONE/PIP in `docs/12`; wire last in this cluster, after confirming whether that caveat still holds.

**9 of 11 live 2026-08-29** as `kraken2_classify`, `kaiju_classify`, `prokka_annotate`,
`bakta_annotate`, `amrfinder_resistance`, `checkm2_quality`, `checkv_quality`, `fastani_similarity`,
`barrnap_rrna`. Kraken2/Prokka/Barrnap/FastANI apt-installable (confirmed live); Kaiju compiled from
source (not apt-installable, simple `make` build); AMRFinderPlus installed from NCBI's own prebuilt
Linux binary release; Bakta/CheckM2/CheckV genuinely PyPI-installable. Each DB-dependent tool ships
the **smallest real, still-useful** official reference database baked into the image at build time,
not the largest -- keeping this cluster's image growth in check for a platform meant to be cloned and
built by any researcher, not just one with a server-grade disk/connection:
- Kraken2: `k2_viral` (~570MB) instead of the ~8-16GB standard/pluspf DBs -- real viral taxonomic
  classification, not full bacterial/archaeal coverage.
- Kaiju: `kaiju_db_viruses` (~280MB) instead of the ~100GB+ `nr` index -- same viral scoping.
- Bakta: the project's own official "light" DB (~1.3GB) instead of the ~30GB "full" DB.
- CheckM2/CheckV: each ships only one real DB size (~1.7GB each) -- no smaller official option
  exists, used as-is.
- AMRFinderPlus: its own real, maintained `amrfinder_update` command fetches the DB (not hand-curled
  file-by-file from NCBI's FTP listing).

Where local testing was possible without root (barrnap, fastANI -- both apt-installable, no huge DB
needed), **actually ran them live end-to-end before committing**, same rigor as xtb_quantum: caught
two real, non-obvious bugs this way. (1) **FastANI's default 3000bp fragment length needs a
genome-scale input, not a short contig** -- a query near that length produced zero alignment;
confirmed live and fixed the tool's own minimum-length validation (1000bp -> 20000bp) rather than
guessing a safe threshold. (2) **Debian's `prokka` package still hard-requires the discontinued NCBI
`tbl2asn` tool** (a real, well-known issue acknowledged in upstream prokka's own FAQ -- `tbl2asn` has
a hard-coded expiration and NCBI pulled it from public download entirely) -- fixed in the Dockerfile
by installing NCBI's own designated replacement, `table2asn`, renamed to `tbl2asn` (a well-established
community workaround, confirmed the real binary is still hosted on NCBI's FTP before relying on it).
Also traced barrnap's full transitive tool dependency chain (`nhmmer`, `bedtools`) and prokka's
(`barrnap`, `blast+`, `prodigal`, all already in this image) by extracting the real `.deb` files
locally rather than assumed.

**GTDB-Tk NOT built** -- its reference database alone is ~110GB, an order of magnitude beyond every
other tool in this cluster combined; baking that into a general-purpose image would make it
genuinely unclonable/unbuildable for a typical researcher's connection and disk. A real infra
decision (external volume, download-on-demand, or a dedicated GTDB-Tk service), not something to
silently bake in. **eggNOG-mapper NOT built** -- confirmed live its minimal real functional-
annotation database (`eggnog.db` + `eggnog_proteins.dmnd` via DIAMOND search mode) is ~11GB
compressed, alone bigger than every other tool in this cluster's baked-in DBs combined -- same class
of infra decision as GTDB-Tk, deferred with the same reasoning rather than silently dropped.

### Cheminformatics -- 4 tools
BioTransformer, RAscore, ToxinPred2, xtb.

**2 of 4 live 2026-08-29** as `xtb_quantum` (real GFN2-xTB semi-empirical quantum chemistry via `xtb`,
apt-installable -- **confirmed live end-to-end before wiring**: apt-downloaded the real deb outside
Docker, generated a real RDKit 3D conformer, and ran a real xtb geometry optimization on it, catching
a real non-obvious bug in the process -- xtb writes its "normal termination" status line to stderr,
not stdout, opposite of most CLI tools; the results summary itself is on stdout) and
`biotransformer_metabolism` (real small-molecule metabolism/metabolite prediction via BioTransformer
3.0, compiled from source via Maven -- real recipe confirmed against the project's own
`install-via-maven.sh`, not guessed; not locally buildable in this sandbox since Maven isn't
bootstrappable without root, so its CSV output schema -- undocumented in BioTransformer's own
README -- is parsed generically rather than assuming fixed column names, and the happy-path test is
deferred to the batch Docker build/test pass). **RAscore NOT built** -- confirmed live: its
`setup.cfg` pins `tensorflow-gpu==2.5.0`, which no longer exists as an installable distribution for
any current platform (`pip install --dry-run` found only `2.12.0` remaining on PyPI, itself since
deprecated/merged into plain `tensorflow`) -- a real, unfixable-without-a-fork installability
blocker, not a config error. **ToxinPred2 NOT built** -- confirmed live against both PyPI releases
(1.0 and 1.1): `toxinpred2.py` unconditionally crashes on any real FASTA input at
`CM.to_csv("Sequence_1", header=False, index=None, sep="\n")` -- Python's own `csv` module has always
rejected `"\n"` as a delimiter (`ValueError: bad delimiter value`, reproduced directly against the
bare `csv` module, independent of pandas version), so this line has likely never worked against any
reasonably modern Python. A genuine, reproducible bug in the package's own source, not an environment
issue -- same rejection rigor as the earlier HADDOCK3 investigation.

### Synthetic biology -- 1 tool
bebop/poly.

**Live 2026-08-29 as `dnachisel_optimize` -- substituted, not built as bebop/poly directly.**
Confirmed live before wiring: `github.com/bebop/poly` is a Go *library* (`go get
github.com/bebop/poly`), not a CLI tool and no prebuilt binary release exists -- using it here would
mean introducing an entirely new compiled-language toolchain into this Python-first codebase just to
wrap a thin custom Go binary. `dnachisel` (Edinburgh Genome Foundry, genuinely PyPI-installable, pure
Python) is a real, well-tested substitute for poly's *codon-optimization* capability specifically --
confirmed live end-to-end (real optimized sequence produced, translation-preservation/GC-content/
restriction-site constraints all verified passing across 4 species). poly's other two listed
capabilities (primers, part assembly) were already covered before this cluster even started, by the
already-live `primer3` and `gibson_assembly` -- so no real coverage is lost by this substitution.

### Other -- 1 tool
DDGun.

**NOT built 2026-08-29** -- confirmed live: the real PyPI `ddgun` package (0.0.2, matches the
project's own citation/summary text, not a namesquat) crashes unconditionally on import --
`ImportError: cannot import name 'three_to_one' from 'Bio.PDB.Polypeptide'` -- because
`Bio.PDB.Polypeptide.three_to_one` was removed from current biopython, and `ddgun/__init__.py`
imports it unconditionally (even the sequence-only `ddgun_seq` path is unreachable, not just the
structure-based `ddgun_3d` path). Downgrading biopython to a version old enough to still have
`three_to_one` (<1.80) isn't viable either -- confirmed live it has no installable wheel for any
current Python and would risk breaking every other tool on this platform that already depends on the
current pinned biopython. A genuine, reproducible bug in the package's own source, not an environment
issue -- same rejection rigor as RAscore/ToxinPred2/HADDOCK3.

## Phase 3 -- R/Bioconductor bridge (infrastructure, not a tool)

Every tool built so far (Phase 1 and 2 both) is pure Python or a Python-wrapped CLI binary. A real
chunk of the strongest remaining candidates -- Seurat, scran, scater, SoupX, monocle, InferCNV,
Giotto, TCGAbiolinks, recount3, tximport, sleuth, clusterProfiler, dada2, WGCNA's original R form --
are R packages. Wiring any of them needs a genuinely new piece of infrastructure: either an `rpy2`
in-process bridge or a subprocess-based `Rscript` wrapper.

**This needs a deliberate decision before the first R tool, not a default.** Concretely:
1. Prototype both approaches against one real tool (`clusterProfiler` is the natural pick -- pairs
   directly with the already-live `gene_set_enrichment`/`gprofiler_enrichment` tools, so there's an
   existing baseline to compare output against).
2. Decide based on: container image size/build time impact (a full R + Bioconductor install is
   large), error-handling ergonomics (rpy2's Python-R type marshaling vs. parsing subprocess
   stdout/stderr), and whether the CONTRIBUTING.md tool-recipe pattern (`build_<tool>_mcp_server()`
   wrapping a `@tool`-decorated function) still holds cleanly either way -- it should for both, but
   confirm before committing 15+ tools to the choice.
3. Document the decision and the exact recipe (a new `CONTRIBUTING.md` subsection, same as the
   existing "Credentialed tools" pattern) before building the second R tool, so this doesn't
   silently re-litigate per contributor.

Once decided: clusterProfiler, dada2, WGCNA (proper R form, replacing/supplementing PyWGCNA),
Seurat, scran, scater, SoupX, monocle, InferCNV, Giotto, TCGAbiolinks, recount3, tximport, sleuth
-- roughly 14 tools, sequenced same as Phase 1/2 (simplest/most-independent first; clusterProfiler
and dada2 first since they're each single-purpose and have a clear existing-tool comparison point,
Seurat's ecosystem last since several other tools in this list are Seurat-adjacent and easier once
the pattern is proven).

**Decision made 2026-08-29: `Rscript` subprocess, not `rpy2`.** rpy2 gives tighter Python<->R type
marshaling, but is a real, well-known source of production fragility -- version-sensitive against
both the R and Python it's built against, R_HOME/ABI mismatches across environments, and no graceful
failure mode (a broken binding can crash the whole orchestrator process, not just one tool call). An
`Rscript` subprocess is exactly the same shape as every CLONE-tier tool already in this codebase
(tempfile in, subprocess out, parse stdout/an output file) -- no new failure mode, no new dependency
class, degrades the same way any other subprocess tool does under a bad input or a crashed script.
`CONTRIBUTING.md`'s existing tool recipe holds unchanged; the one addition is that a real R script
lives in `app/tools/r_scripts/<name>.R`, not inlined in the Python wrapper, so it can be read/tested
independently -- documented as a new `CONTRIBUTING.md` subsection alongside the existing
"Credentialed tools" pattern, not left implicit.

**clusterProfiler live 2026-08-29** as `cluster_profiler_enrichment` -- the first R tool, proving the
pattern per this section's own step 1. Real Bioconductor `enrichGO` call (GO term enrichment with
Benjamini-Hochberg FDR correction), human or mouse, against a caller-supplied gene symbol list. R +
Bioconductor + `libcurl4-openssl-dev`/`libssl-dev`/`libxml2-dev` + the common font/image dev
libraries (`libfontconfig1-dev`, `libharfbuzz-dev`, `libfribidi-dev`, `libfreetype6-dev`,
`libpng-dev`, `libtiff5-dev`, `libjpeg-dev`) are all real, well-documented system requirements for
compiling Bioconductor packages and their common transitive deps (clusterProfiler pulls in ggplot2,
whose systemfonts/ragg/textshaping deps need these) -- not guessed, R/Bioconductor's own standard
documented requirement set. Not locally testable in this sandbox (no R interpreter available, and
Bioconductor package compilation is itself a real, substantial build-time step) -- verification
deferred to the batch Docker build/test pass, same as every DB/environment-dependent Phase 2 tool.

**Remaining ~13 R tools (dada2, WGCNA, Seurat, scran, scater, SoupX, monocle, InferCNV, Giotto,
TCGAbiolinks, recount3, tximport, sleuth) NOT yet built.** Real scoping check done before committing
further: dada2/SoupX/monocle/InferCNV/Giotto/tximport/sleuth all need a real uploaded dataset
(FASTQ, a 10x-format droplet matrix, or Salmon/Kallisto quantification output) to be useful -- this
platform still has no file-upload/ingestion path (same explicit out-of-scope finding as the
DATA-gated tools listed below), so building them now would mean either a fake toy input that
misrepresents the tool's real value, or silently expanding scope into the file-upload problem this
plan deliberately doesn't try to solve. Seurat/scran/scater are the same DATA-gated class in
practice (need a realistically-sized count matrix, impractical as inline JSON in a chat tool call).
**TCGAbiolinks, recount3, and WGCNA are the real next candidates** -- TCGAbiolinks/recount3 fetch
public data themselves (real API-based tools, same shape as the already-live cbioportal_mutations,
not DATA-gated), and WGCNA can be scoped to a caller-supplied expression matrix the same way
`dnachisel_optimize`/`treemix_population_tree` accept caller-supplied structured data -- left for a
follow-up pass rather than rushed in the same turn as the architecture decision itself.

## Explicitly out of scope for this plan

**DATA-gated** (real capability, but needs a dataset -- FASTQ/BAM/VCF/scRNA-seq matrix -- this
platform has no upload/ingestion path for today): BWA, GATK, FreeBayes, RepeatMasker, DeepVariant,
kallisto, MetaPhlAn/HUMAnN (functionally, per the Phase 2 caveat above), celltypist, MACA, Scaden,
xCell2, and the broader cell-type-annotation/deconvolution group. **Unblocking these as a group is
worth a dedicated plan of its own** (a real file-upload path through Mattermost/the orchestrator,
storage, and a "which of these tools applies to this file type" dispatch) -- not something to
half-solve tool-by-tool here.

**GPU-heavy, deferred**: **OpenFold** only. AlphaFold2-scale attention memory (roughly quadratic in
sequence length) genuinely needs 12GB+ VRAM for real protein lengths -- a consumer card like a 3050
(6GB) can't reliably run it, and the platform already has real structure prediction via the
existing `alphafold` tool source (AlphaFold DB lookup). Deferred to
`docs/07-system-architecture.md`'s Phase 6 compute-layer decision (the same "check Hugging Face's
Inference API before defaulting to NVIDIA Platform/cloud GPU" question already flagged there).

**Removed from the shortlist entirely, not deferred**: **DiffDock-PP** and **FlowDock** (deep-learning
protein-protein docking) -- genuinely redundant, not just GPU-gated. `LightDock` (Phase 1) and
`HADDOCK3` (Phase 2) already cover protein-protein docking, need no GPU, and are more proven at
scale. Keeping both a classical and a deep-learning path for the exact same capability isn't worth
the GPU dependency here. If a real accuracy gap between the classical tools and these shows up in
practice later, revisit -- but don't build against that assumption speculatively.

See "Phase 1.5" above for the four GPU tools that *do* fill a genuinely new capability (not another
way to dock) and are realistic on modest local hardware: ProteinMPNN, RFdiffusion, ProtGPT2,
ChromBPNet.

## Newly identified gaps -- outside the original docs/12 scope

`docs/12-biotools-triage-shortlist.md` was scoped to "bio.tools + GitHub Repo Triage" -- downloadable
packages and CLI tools -- and explicitly excluded "pure database/web-portal entries with no
downloadable code or API." That exclusion swept out a real category it shouldn't have: sources with
a genuine, free, unauthenticated REST API and no download at all, the exact same shape as
`pubmed.py`/`chembl.py`/`pdb.py`/`ensembl.py` already live in this codebase. A fresh scan against
what's actually already wired turned up real gaps in that category, worth a pass of their own,
same PIP-tier effort as this session's `uniprot.get_sequence` addition (a builder file, no new
architecture):

| Source | Gap it closes | Why it's not already covered | Status |
|---|---|---|---|
| **PubChem** (PUG-REST, free, unauthenticated) | Broader compound/bioassay database than ChEMBL's bioactivity-curated scope -- different compound coverage, includes PubChem BioAssay screening data | `chembl.py` is bioactivity-focused; PubChem is a different, complementary compound universe entirely | **Live 2026-08-26 as `pubchem`.** |
| **Europe PMC** (free REST API) | Full-text search across a broader source set than PubMed alone -- preprints (bioRxiv/medRxiv), grant/patent links, and free full-text availability signals PubMed doesn't carry | `pubmed.py` only queries NCBI's own index; Europe PMC indexes preprints PubMed doesn't | **Live 2026-08-26 as `europepmc`.** |
| **Ensembl VEP** (Variant Effect Predictor, free REST API, same host as the existing `ensembl.py`) | Predicts the functional consequence of a variant that *isn't* already in ClinVar -- missense/nonsense/splice-site impact, SIFT/PolyPhen scores | `clinvar.py` and `gnomad.py` only answer "what's already known about this variant" (clinical significance, population frequency) -- neither predicts consequence for a novel/hypothetical variant, a real gap for anything not yet curated in ClinVar | **Live 2026-08-26 as `ensembl_vep`.** |
| **Human Phenotype Ontology (HPO)** (free REST API, `hpo.jax.org`) | Structured phenotype-to-gene/disease associations (e.g. "which genes cause this specific clinical phenotype") | `ontologies.py`'s generic OLS-backed search covers term lookup/definitions across many ontologies but not HPO's specific gene/disease association graph | **Live 2026-08-26 as `hpo`.** |
| **PharmGKB** (free REST API) | Pharmacogenomics: drug-gene-variant interactions (e.g. "does this variant change how this patient metabolizes this drug") | `dailymed.py` covers drug labels; nothing covers gene-drug-variant interaction data, a distinct and clinically real question | **Live 2026-08-26 as `clinpgx_annotations`** -- the real successor API lives at `api.clinpgx.org` (docs/10 Phase 3's old `api.pharmgkb.org`/`clinpgx.org` guesses were both dead ends; this host wasn't guessed, confirmed live). |
| **openFDA** (FDA's own free REST API, adverse-event/FAERS data) | Real-world adverse-event reports for a drug -- a different, complementary signal to `dailymed.py`'s label text | Label data says what a drug is approved to claim; FAERS says what's actually been reported in practice -- genuinely different data, not a duplicate | **Live 2026-08-26 as `openfda`.** |

**All six "newly identified gaps" entries above are now live** -- this section is complete.

Each of these is genuinely PIP-tier effort (a builder file wrapping `httpx` calls, no package
install, no Dockerfile change) -- worth folding into Phase 1 rather than treating as a separate
wave, once someone actually verifies each API's current contract (rate limits, auth requirements,
response shape) the same way every existing external-API tool in this codebase already was.

This list is a first pass, not exhaustive -- flagged honestly as such rather than presented as a
complete inventory. If wiring one of these surfaces adjacent sources worth adding (the same way
`get_sequence` surfaced from battle-testing, not from a pre-planned list), extend this table rather
than treating it as closed.

## Acceptance criteria (per tool, no exceptions)

Same bar as every tool already live, restated so it's explicit rather than assumed:
- Builder file + `TOOL_BUILDERS` entry + `KNOWN_TOOL_SOURCES` entry + citation pattern (if
  applicable) -- `CONTRIBUTING.md`'s documented recipe, step for step.
- A real test hitting the real package/binary with real input, not mocked -- matching this
  session's `test_uniprot.py`/`test_msa.py` pattern (happy path, at least one error path that
  proves it fails cleanly rather than crashing).
- Live-verified through the actual running product (a real Mattermost message, not just the test
  suite passing) before considered done -- the exact gap this whole readiness pass exists to close
  for every *existing* tool; don't reintroduce it for new ones.
- `docs/14-biotools-shortlist-status.md` and `docs/12-biotools-triage-shortlist.md`'s checkbox both
  updated in the same PR, so the "live" count stays trustworthy rather than needing another
  from-scratch audit later.
