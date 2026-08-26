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
| AbLang | Antibody sequence language model |
| BioPhi | Antibody humanization + humanness scoring |
| PyIR | Antibody/TCR V(D)J gene assignment (IgBLAST wrapper) |
| clusTCR | TCR repertoire clustering |
| tcrdist3 | TCR repertoire distance metrics |

### Cheminformatics (`feature/cheminformatics`) -- 7 tools
| Tool | Adds |
|---|---|
| LightDock | Protein-protein docking (Vina only does small-molecule). **Live 2026-08-26 as `lightdock_docking`.** |
| Auto3D | SMILES -> 3D conformers (closes the gap between ChEMBL's 2D SMILES and Vina's 3D input requirement). **Live 2026-08-26 as `auto3d_conformers`.** Found and guarded against a real, environment-specific bug: torch's JIT C++ compile (inductor) fails when the install path contains a space (`TORCHDYNAMO_DISABLE=1` set at import time). |
| AiZynthFinder | Retrosynthetic route planning -- not attempted this pass (time budget), real pretrained-model download risk similar to HunFlair's, worth its own session. |
| Chemprop | Trainable/pretrained molecular property prediction (MPNN) -- not attempted this pass; needs a pretrained checkpoint or training data this platform doesn't have on hand, not a simple zero-shot wrap like the other tools here. |
| ~~Pickaxe~~ | Metabolite/biotransformation prediction from a structure. **Checked 2026-08-26, not built.** The real PyPI package is `minedatabase` (bare `pickaxe` on PyPI is an empty placeholder, confirmed before installing). It pulls a heavy, unexpected dependency chain (pymongo, keras) suggesting the package is architected around a persistent MongoDB-backed reaction database, not a stateless per-request computation, and its `lxml` dependency fails to build without `libxml2-dev`/`libxslt1-dev` system headers (not in the base image). A heavier CLONE-tier integration than docs/12 assumed -- worth a dedicated pass to confirm whether standalone (non-Mongo) use is actually viable, not built speculatively here. |
| libRoadRunner | SBML kinetic/ODE simulation (dynamic, complements cobrapy's steady-state FBA) |
| basico | Same SBML kinetic simulation niche, alternate API |

### Population genetics (`feature/population-genetics`) -- 3 tools
| Tool | Adds |
|---|---|
| pixy | Nucleotide diversity (pi) / divergence (dxy) from a VCF |
| egglib | General pop-gen stats engine (diversity, Fst, Tajima's D) |
| pandasGWAS | Programmatic GWAS Catalog queries |

### Sequence analysis (`feature/sequence-analysis`) -- 1 tool
| Tool | Adds |
|---|---|
| Minimap2 / mappy | Versatile pairwise aligner (long reads, cDNA, genome-vs-genome) |

### Synthetic biology (`feature/synthetic-biology`) -- 2 tools
| Tool | Adds |
|---|---|
| OpenCloning | Cloning/genome-engineering strategy design (documented API) |
| PEGG | Prime-editing pegRNA design |

### Transcriptomics (`feature/transcriptomics`) -- 6 tools
| Tool | Adds |
|---|---|
| SCANPY | Field-standard Python scRNA-seq toolkit (QC, clustering, trajectory, DE) -- **DATA-gated in practice**: real capability, but needs an actual expression matrix input; wire the tool now, note the same data-ingestion caveat as the DATA-gated list below applies to how *useful* it is until a matrix-upload story exists |
| pyComBat | Batch-effect correction |
| scVelo | RNA velocity (cell-state transition dynamics) |
| HunFlair (flair) | Biomedical NER from free text -- real near-term win: auto-tag entities in PubMed/OpenAlex results, no data-ingestion dependency at all |
| OmniPath | Integrated signaling pathways + ligand-receptor cell communication (distinct from STRING/KEGG/Reactome, which this platform already has) |
| BUSCO | Genome/transcriptome/proteome assembly completeness scoring |

### Structural biology (`feature/structural-biology`) -- 4 tools
| Tool | Adds |
|---|---|
| DockQ | Docking pose quality scoring -- pairs directly with the existing `vina_docking`/`plip_interactions` chain |
| spyrmsd | Pose RMSD scoring, same pairing |
| IDPConformerGenerator | 3D conformer ensembles for intrinsically disordered regions from sequence |
| correlationplus | Dynamical/allosteric residue correlation from a static structure (Elastic Network Model, no MD trajectory needed) |

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

### Structural biology -- 6 tools
Fpocket, US-align, Foldseek, FoldMason, DSSP, HADDOCK3.

### Phylogenetics -- 4 tools
FastTree, OrthoFinder, PAML, ASTRAL-Pro2.

### Population genetics -- 6 tools
poolfstat, ADMIXTURE, Eigensoft, TreeMix, selscan, LDSC.

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

### Cheminformatics -- 4 tools
BioTransformer, RAscore, ToxinPred2, xtb.

### Synthetic biology -- 1 tool
bebop/poly.

### Other -- 1 tool
DDGun.

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
