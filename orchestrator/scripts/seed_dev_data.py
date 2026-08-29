"""Seeds one Org + the one master Agent for local dev, matching whatever
scripts/bootstrap_mattermost.py created (docs/10-build-plan.md). Also wires
TOOL_BINDING rows for every tool source named --tools (default: every real
tool source this script knows about -- see ALL_KNOWN_TOOLS below), creating
the ToolSource if it doesn't exist yet. Idempotent -- safe to re-run
(updates the bot token/name/tool bindings if they changed).

The default used to be just "pubmed" -- a real gap for anyone following
README.md's Getting Started end to end with no other guidance: the agent
would come up able to answer exactly one kind of question, while every
other capability the README itself advertises (docking, structure
prediction, variant lookups, pathway analysis, ...) silently wasn't bound
at all, with no error anywhere to say so. Binding every known tool source
by default is what makes README's own "what you can actually ask it today"
table true out of the box; pass --tools explicitly only to bind a
deliberately narrower subset.

There's exactly one Agent per org now (the architecture pivot, see
07-system-architecture.md) -- this script no longer takes a --cluster
flag; "cluster" on the Agent model is vestigial post-pivot
(06-data-model.md).

Usage:
  .venv/bin/python scripts/seed_dev_data.py \\
    --team-id <mattermost_team_id> --bot-user-id <bot_user_id> \\
    --bot-token <bot_access_token> [--name "OpenBioLab"] [--tools pubmed,chembl,...]
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import async_session  # noqa: E402
from app.models import Agent, Org, ToolBinding, ToolSource  # noqa: E402
from app.vault import encrypt  # noqa: E402

# name -> (category, access_model, mcp_server_ref, requires_expert_review,
# requires_credential) for tool sources this script knows how to create.
# requires_expert_review is docs/05-ux-behavior.md Section 4's marker:
# True for clinical/regulatory-sensitive sources (clinical variant
# databases, trial registries, drug labels, FAERS). requires_credential
# marks a BYO-paid-credential tool source (app/vault.py's Credential
# vault, Section 8) -- a row can exist here and be bound to the agent
# with mcp_server_ref pointing at nothing real yet (no TOOL_BUILDERS
# entry in app/tool_roster.py): build_tool_roster() silently skips any
# ToolSource with no matching builder, so a placeholder row is inert
# until a real tool file + credential exist, not a live broken tool.
KNOWN_TOOL_SOURCES = {
    "pubmed": ("literature", "free_public", "in-process:app.tools.pubmed", False, False),
    "chembl": ("drug_discovery", "free_public", "in-process:app.tools.chembl", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Cheminformatics
    # cluster -- real SMILES -> 3D conformer generation (RDKit isomer
    # enumeration + AIMNET NNP optimization), closes the gap between
    # ChEMBL/PubChem's 2D SMILES and vina_docking's 3D input requirement.
    "auto3d_conformers": ("drug_discovery", "free_public", "in-process:app.tools.auto3d_conformers", False, False),
    # docs/17-remaining-tools-wiring-plan.md "newly identified gaps" --
    # real, free, unauthenticated REST APIs outside docs/12's original
    # bio.tools/GitHub triage scope.
    "pubchem": ("drug_discovery", "free_public", "in-process:app.tools.pubchem", False, False),
    # docs/17-remaining-tools-wiring-plan.md's Other cluster -- real
    # cancer-genomics mutation data across public TCGA/cBioPortal
    # studies, a different question than ClinVar/gnomAD (population/
    # clinical significance) answer: how often is this gene actually
    # mutated in real patient tumor cohorts. cptac (same cluster) tried
    # and NOT wired -- see docs/17 for why (phones home to Zenodo on
    # bare import, observed to hang/504 repeatedly, unsuitable for a
    # per-request tool call).
    "cbioportal_mutations": ("drug_discovery", "free_public", "in-process:app.tools.cbioportal_mutations", False, False),
    "europepmc": ("literature", "free_public", "in-process:app.tools.europepmc", False, False),
    "open_targets": ("drug_discovery", "free_public", "in-process:app.tools.open_targets", False, False),
    "literature_discovery": ("literature", "free_public", "in-process:app.tools.literature_discovery", False, False),
    "ensembl": ("genomics", "free_public", "in-process:app.tools.ensembl", False, False),
    # Predicts a variant's functional consequence (missense/nonsense/
    # splice-site, SIFT/PolyPhen) for a variant not yet curated in
    # ClinVar -- clinical-adjacent, same review tier as clinvar/gnomad.
    "ensembl_vep": ("genomics", "free_public", "in-process:app.tools.ensembl_vep", True, False),
    "uniprot": ("genomics", "free_public", "in-process:app.tools.uniprot", False, False),
    "clinvar": ("genomics", "free_public", "in-process:app.tools.clinvar", True, False),
    # Real successor to the old, now-dead pharmgkb.org API (docs/10 Phase
    # 3 gave up on it) -- api.clinpgx.org confirmed live 2026-08-26.
    # Pharmacogenomics is clinically actionable -- same review tier.
    "clinpgx_annotations": ("clinical", "free_public", "in-process:app.tools.clinpgx_annotations", True, False),
    "gnomad": ("genomics", "free_public", "in-process:app.tools.gnomad", False, False),
    "ontologies": ("ontologies", "free_public", "in-process:app.tools.ontologies", False, False),
    "hpo": ("ontologies", "free_public", "in-process:app.tools.hpo", False, False),
    "kegg": ("systems_biology", "free_public", "in-process:app.tools.kegg", False, False),
    "reactome": ("systems_biology", "free_public", "in-process:app.tools.reactome", False, False),
    # docs/18-platform-capability-gaps.md Pass 2 #1 -- correctness/trust
    # fix for the existing grounded-response guarantee, not a new domain.
    # Real structured retraction data from PubMed's own record (not a
    # heuristic), no external API dependency beyond E-utilities (already
    # used by pubmed.py). requires_expert_review=True: a retraction
    # finding is itself a fact a researcher needs to see flagged, same
    # tier as clinical variant/trial/label data.
    "retraction_watch": ("literature", "free_public", "in-process:app.tools.retraction_watch", True, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Cheminformatics
    # cluster -- dynamic SBML kinetic simulation via libRoadRunner,
    # complementing cobra_fba's steady-state FBA. basico deliberately not
    # also wired -- docs/17 itself flags it as "same niche, alternate API".
    "kinetic_simulation": ("systems_biology", "free_public", "in-process:app.tools.kinetic_simulation", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Population genetics
    # cluster -- real local diversity-statistics computation, natural
    # downstream step from the already-live msa tool's aligned output.
    "egglib_popgen": ("population_genetics", "free_public", "in-process:app.tools.egglib_popgen", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 2, Population genetics
    # cluster. poolfstat NOT built here -- CRAN-only (real R package, no
    # Python distribution), belongs in Phase 3's R/Bioconductor bridge
    # once that architecture (rpy2 vs. subprocess Rscript) is decided,
    # not this CLONE-tier batch. pixy NOT built -- confirmed again live:
    # not apt-installable, not on PyPI (the PyPI `pixy` package is an
    # unrelated terminal-color library), no GitHub release binary either
    # -- still genuinely bioconda-only.
    "eigensoft_pca": ("population_genetics", "free_public", "in-process:app.tools.eigensoft_pca", False, False),
    "admixture_ancestry": ("population_genetics", "free_public", "in-process:app.tools.admixture_ancestry", False, False),
    "treemix_population_tree": ("population_genetics", "free_public", "in-process:app.tools.treemix_population_tree", False, False),
    "selscan_nsl": ("population_genetics", "free_public", "in-process:app.tools.selscan_nsl", False, False),
    "ldsc_genetic_correlation": ("population_genetics", "free_public", "in-process:app.tools.ldsc_genetic_correlation", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 2 Population genetics
    # cluster -- both re-investigated after their earlier deferral/
    # rejection, per explicit direction to add back the important ones.
    # pixy: confirmed live it's real, actively-maintained pure Python
    # under the hood despite being conda-forge-only distributed -- pip
    # installed from source (its own calc_pi/calc_dxy called in-process
    # on a caller-built scikit-allel GenotypeArray, no VCF/CLI needed).
    # poolfstat: real R tool, now buildable via the R/Bioconductor bridge.
    "pixy_diversity": ("population_genetics", "free_public", "in-process:app.tools.pixy_diversity", False, False),
    "poolfstat_fst": ("population_genetics", "free_public", "in-process:app.tools.poolfstat_fst", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 2, Metagenomics
    # cluster -- the heaviest remaining cluster, several tools needing
    # real multi-GB reference databases baked into the image at build
    # time (see Dockerfile). Each database was deliberately chosen as
    # the smallest real, still-useful official option (e.g. Kraken2's
    # k2_viral instead of the ~8-16GB standard DB, Bakta's official
    # "light" DB instead of "full") to keep image growth in check for a
    # platform meant to be cloned and built by any researcher.
    # GTDB-Tk NOT built -- its reference DB alone is ~110GB, an order of
    # magnitude beyond every other tool in this cluster combined; a real
    # infra decision (external volume/download-on-demand), not something
    # to bake into a general-purpose image. eggNOG-mapper NOT built --
    # confirmed live its minimal real functional-annotation DB
    # (eggnog.db + eggnog_proteins.dmnd) is ~11GB compressed, alone
    # bigger than every other tool in this cluster combined; same class
    # of infra decision as GTDB-Tk, deferred rather than silently
    # dropped. Real, confirmed-live gotcha found and fixed for Prokka:
    # Debian's `prokka` package still hard-requires the discontinued
    # NCBI `tbl2asn` (hard-coded expiration, pulled from public
    # download) -- fixed in the Dockerfile via NCBI's own designated
    # replacement, `table2asn`, renamed to `tbl2asn`.
    "kraken2_classify": ("metagenomics", "free_public", "in-process:app.tools.kraken2_classify", False, False),
    "kaiju_classify": ("metagenomics", "free_public", "in-process:app.tools.kaiju_classify", False, False),
    "prokka_annotate": ("metagenomics", "free_public", "in-process:app.tools.prokka_annotate", False, False),
    "bakta_annotate": ("metagenomics", "free_public", "in-process:app.tools.bakta_annotate", False, False),
    "amrfinder_resistance": ("metagenomics", "free_public", "in-process:app.tools.amrfinder_resistance", False, False),
    "checkm2_quality": ("metagenomics", "free_public", "in-process:app.tools.checkm2_quality", False, False),
    "checkv_quality": ("metagenomics", "free_public", "in-process:app.tools.checkv_quality", False, False),
    "fastani_similarity": ("metagenomics", "free_public", "in-process:app.tools.fastani_similarity", False, False),
    "barrnap_rrna": ("metagenomics", "free_public", "in-process:app.tools.barrnap_rrna", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Sequence analysis
    # cluster -- real minimap2 pairwise alignment (long reads/cDNA/
    # genome-vs-genome), complementing msa's MAFFT multiple-sequence
    # alignment of closely-related sequences.
    "minimap2_align": ("sequence_analysis", "free_public", "in-process:app.tools.minimap2_align", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 2, Sequence analysis
    # fundamentals cluster (highest-priority cluster in that phase) --
    # BLAST+ is flagged in docs/12 as "the single most fundamental
    # missing operation"; this platform had zero sequence-similarity-
    # search capability before these five.
    "blast_search": ("sequence_analysis", "free_public", "in-process:app.tools.blast_search", False, False),
    "diamond_search": ("sequence_analysis", "free_public", "in-process:app.tools.diamond_search", False, False),
    "clustalo_align": ("sequence_analysis", "free_public", "in-process:app.tools.clustalo_align", False, False),
    "emboss_water": ("sequence_analysis", "free_public", "in-process:app.tools.emboss_water", False, False),
    "prodigal_genes": ("sequence_analysis", "free_public", "in-process:app.tools.prodigal_genes", False, False),
    "mummer_align": ("sequence_analysis", "free_public", "in-process:app.tools.mummer_align", False, False),
    "string": ("systems_biology", "free_public", "in-process:app.tools.string_db", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Transcriptomics
    # cluster -- real directed/signed signaling interactions with
    # literature evidence, distinct from kegg/reactome (pathway detail)
    # and string (undirected confidence network).
    "omnipath_interactions": ("systems_biology", "free_public", "in-process:app.tools.omnipath_interactions", False, False),
    "clinicaltrials": ("clinical", "free_public", "in-process:app.tools.clinicaltrials", True, False),
    "dailymed": ("clinical", "free_public", "in-process:app.tools.dailymed", True, False),
    # Real-world adverse-event reports (FAERS) -- clinical/regulatory-
    # sensitive, same tier as dailymed/clinicaltrials.
    "openfda": ("clinical", "free_public", "in-process:app.tools.openfda", True, False),
    "pdb": ("structural_biology", "free_public", "in-process:app.tools.pdb", False, False),
    "alphafold": ("structural_biology", "free_public", "in-process:app.tools.alphafold", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Immunoinformatics
    # cluster -- all three real local computation, no external API.
    "epitopepredict": ("immunoinformatics", "free_public", "in-process:app.tools.epitopepredict", False, False),
    "anarci_numbering": ("immunoinformatics", "free_public", "in-process:app.tools.anarci_numbering", False, False),
    "tcrdist_repertoire": ("immunoinformatics", "free_public", "in-process:app.tools.tcrdist_repertoire", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Immunoinformatics
    # cluster -- real AbLang model inference (restore mode) on caller-
    # supplied masked antibody sequences, no external API.
    "ablang_restore": ("immunoinformatics", "free_public", "in-process:app.tools.ablang_restore", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1 Immunoinformatics
    # cluster, reclassified to Phase 2 CLONE-tier plumbing -- confirmed
    # live it genuinely shells out to a real igblastn binary + germline
    # reference DBs (bare `pyir` on PyPI is unrelated; real package is
    # `crowelab-pyir`). Real, confirmed-live packaging defect found and
    # fixed in the Dockerfile: Debian's `igblast` apt package ships only
    # NCBI C++ toolkit build utilities, not the actual igblastn/igblastp
    # executables -- installed from NCBI's own official binary release
    # instead.
    "pyir_annotate": ("immunoinformatics", "free_public", "in-process:app.tools.pyir_annotate", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Population genetics
    # cluster -- real NHGRI-EBI GWAS Catalog study/trait lookup for a
    # variant, distinct from ensembl_vep/gnomad/open_targets. Genuinely
    # slow (60-180s per call, confirmed live) -- expected, not a bug.
    "gwas_catalog": ("population_genetics", "free_public", "in-process:app.tools.gwas_catalog", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Synthetic biology
    # cluster (in place of OpenCloning, which is a FastAPI backend, not
    # a callable library -- see app/tools/gibson_assembly.py). Real
    # pydna Gibson assembly simulation, no external API.
    "gibson_assembly": ("synthetic_biology", "free_public", "in-process:app.tools.gibson_assembly", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 2, Synthetic biology
    # cluster -- real constraint-based codon optimization via dnachisel,
    # wired in place of the docs/12-listed "bebop/poly" (confirmed live:
    # that's a Go *library* with no CLI/prebuilt binary, would need an
    # entirely new compiled-language toolchain just to wrap a thin custom
    # Go binary; primer3/gibson_assembly already cover poly's other two
    # listed capabilities). DDGun NOT built -- confirmed live: the real
    # PyPI `ddgun` 0.0.2 package unconditionally crashes on import
    # (`ImportError: cannot import name 'three_to_one' from
    # 'Bio.PDB.Polypeptide'` -- removed from current biopython; no
    # working biopython<1.80 wheel exists for a current Python either).
    "dnachisel_optimize": ("synthetic_biology", "free_public", "in-process:app.tools.dnachisel_optimize", False, False),
    # free_metered, not free_public -- HF's Inference API needs a real
    # (free-to-create) token, unlike the NCBI/EBI/RCSB-style truly
    # anonymous APIs everything else here uses.
    "huggingface": ("compute", "free_metered", "in-process:app.tools.huggingface", False, True),
    # Wrapped local libraries (docs/10-build-plan.md Phase 5's bio.tools +
    # GitHub-repo triage) -- real in-process computation, no external API.
    "scikit_bio": ("microbiome", "free_public", "in-process:app.tools.scikit_bio", False, False),
    # docs/12-biotools-triage-shortlist.md's Metagenomics / microbiology
    # cluster (feature/metagenomics branch) -- real in-process MinHash
    # comparison (sourmash), no external API for the computation. The
    # rest of this cluster (eggNOG-mapper, CheckM2, MetaPhlAn) needs
    # multi-GB reference databases or a heavy TensorFlow dependency chain,
    # not pursued this pass -- see docs/10-build-plan.md for the finding.
    "sourmash_compare": ("microbiome", "free_public", "in-process:app.tools.sourmash_compare", False, False),
    "biopandas_structure": ("structural_biology", "free_public", "in-process:app.tools.biopandas_structure", False, False),
    "cobra_fba": ("systems_biology", "free_public", "in-process:app.tools.cobra_fba", False, False),
    "vina_docking": ("drug_discovery", "free_public", "in-process:app.tools.vina_docking", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Cheminformatics
    # cluster -- real protein-protein docking (LightDock glowworm swarm
    # optimization), complementing vina_docking's small-molecule-only
    # scope.
    "lightdock_docking": ("drug_discovery", "free_public", "in-process:app.tools.lightdock_docking", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Structural biology
    # cluster -- real symmetry-corrected small-molecule pose RMSD, pairs
    # with vina_docking. DockQ (protein-protein pose scoring, same
    # shortlist row) investigated and NOT wired -- see docs/17 for why
    # (hard numpy<2 vs. msprime/tskit's numpy>=2 C-API conflict).
    "spyrmsd_pose": ("structural_biology", "free_public", "in-process:app.tools.spyrmsd_pose", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Structural biology
    # cluster -- real allostery/flexibility signal (Elastic Network
    # Model) from a single static structure, no MD trajectory needed.
    "correlationplus_dynamics": (
        "structural_biology", "free_public", "in-process:app.tools.correlationplus_dynamics", False, False,
    ),
    # docs/17-remaining-tools-wiring-plan.md Phase 2, Structural biology
    # cluster. HADDOCK3 (haddock3_docking, same cluster) investigated
    # and NOT built -- confirmed live via strace that its topoaa
    # module's CNS jobs exit cleanly (code 0) but haddock3's own Python
    # wrapper never writes/uses the captured CNS output, so every run
    # fails with "100% of output not generated" regardless of input --
    # a real bug/breakage in the current PyPI release (2026.8.0), not a
    # config error on this platform's side.
    "dssp_secondary_structure": ("structural_biology", "free_public", "in-process:app.tools.dssp_secondary_structure", False, False),
    "foldseek_search": ("structural_biology", "free_public", "in-process:app.tools.foldseek_search", False, False),
    "usalign_tmscore": ("structural_biology", "free_public", "in-process:app.tools.usalign_tmscore", False, False),
    "foldmason_align": ("structural_biology", "free_public", "in-process:app.tools.foldmason_align", False, False),
    "fpocket_detection": ("structural_biology", "free_public", "in-process:app.tools.fpocket_detection", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 2, Phylogenetics
    # cluster -- fasttree/paml apt-installable (confirmed live before
    # assuming); astral_pro_tree compiled from ASTER's Linux branch
    # (docs/17 named it "ASTRAL-Pro2", the project has since moved to
    # ASTRAL-Pro3, confirmed via its own README); orthofinder_groups
    # installed from its own self-contained release tarball (not on
    # apt or PyPI, confirmed live).
    "fasttree_tree": ("phylogenetics", "free_public", "in-process:app.tools.fasttree_tree", False, False),
    "orthofinder_groups": ("phylogenetics", "free_public", "in-process:app.tools.orthofinder_groups", False, False),
    "paml_yn00": ("phylogenetics", "free_public", "in-process:app.tools.paml_yn00", False, False),
    "astral_pro_tree": ("phylogenetics", "free_public", "in-process:app.tools.astral_pro_tree", False, False),
    # docs/12-biotools-triage-shortlist.md's Sequence analysis fundamentals
    # cluster (feature/sequence-analysis branch) -- both real in-process
    # computation, no external API for the computation itself.
    "primer3": ("sequence_analysis", "free_public", "in-process:app.tools.primer3", False, False),
    "pyhmmer_search": ("sequence_analysis", "free_public", "in-process:app.tools.pyhmmer_search", False, False),
    # Real gap found by battle-testing every pipeline with hard questions
    # (docs/15-battle-test-report.md, Battle 7): phylogenetics.
    # build_phylogenetic_tree assumes pre-aligned input and has no way to
    # align raw sequences itself -- feeding it real, indel-bearing
    # sequences silently corrupted a tree result instead of erroring.
    # Real in-process wrap of the `mafft` CLI (installed via apt in
    # Dockerfile), no external API for the computation itself.
    "msa": ("sequence_analysis", "free_public", "in-process:app.tools.msa", False, False),
    # docs/12-biotools-triage-shortlist.md's Population genetics cluster
    # (feature/population-genetics branch) -- real in-process coalescent
    # simulation (msprime + tskit), no external API for the computation.
    "msprime": ("population_genetics", "free_public", "in-process:app.tools.msprime", False, False),
    # docs/12-biotools-triage-shortlist.md's Structural biology / docking
    # cluster (feature/structural-biology branch) -- real in-process PLIP
    # analysis, no external API for the computation. Natural pair with
    # vina_docking: Vina scores a pose, PLIP explains it.
    "plip_interactions": ("structural_biology", "free_public", "in-process:app.tools.plip_interactions", False, False),
    # docs/12-biotools-triage-shortlist.md's Immunoinformatics cluster
    # (feature/immunoinformatics branch) -- real local model inference
    # (pretrained pan-allele neural net, CPU-only), no external API.
    "mhcflurry_binding": ("immunoinformatics", "free_public", "in-process:app.tools.mhcflurry_binding", False, False),
    # docs/12-biotools-triage-shortlist.md's Transcriptomics cluster
    # (feature/transcriptomics branch) -- both query real, live enrichment
    # services (Enrichr, g:Profiler), independent backends kept as two
    # tools deliberately so results can cross-check each other.
    "gene_set_enrichment": ("transcriptomics", "free_public", "in-process:app.tools.gene_set_enrichment", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Transcriptomics
    # cluster -- real ComBat batch-effect correction on caller-supplied
    # expression data, no external API.
    "pycombat_correction": ("transcriptomics", "free_public", "in-process:app.tools.pycombat_correction", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Transcriptomics
    # cluster -- real Scanpy QC/normalize/PCA/neighbors/Leiden pipeline
    # on caller-supplied count matrices. DATA-gated in practice (no real
    # scRNA-seq-matrix ingestion path exists yet) but wired now per
    # docs/17's explicit call, so it's real and tested once that exists.
    "scanpy_clustering": ("transcriptomics", "free_public", "in-process:app.tools.scanpy_clustering", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Transcriptomics
    # cluster -- real HunFlair2 (flair) biomedical NER on caller-supplied
    # free text (genes/diseases/chemicals/species/cell lines), local
    # model inference, no external API per request.
    "hunflair_ner": ("transcriptomics", "free_public", "in-process:app.tools.hunflair_ner", False, False),
    "gprofiler_enrichment": ("transcriptomics", "free_public", "in-process:app.tools.gprofiler_enrichment", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 3 -- the R/
    # Bioconductor bridge's first tool, proving the Rscript-subprocess
    # architecture decision (see app/tools/cluster_profiler_enrichment.py
    # for the full rpy2-vs-Rscript reasoning) before committing the
    # rest of that cluster (WGCNA, TCGAbiolinks, recount3, ... -- see
    # docs/17) to the same pattern.
    "cluster_profiler_enrichment": ("transcriptomics", "free_public", "in-process:app.tools.cluster_profiler_enrichment", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 3 -- the R/
    # Bioconductor bridge's next real candidates after clusterProfiler:
    # TCGAbiolinks/recount3 fetch public data themselves (GDC REST API /
    # recount3's own study catalog), WGCNA works from a caller-supplied
    # expression matrix -- none are DATA-gated the way most of the
    # remaining R-bridge candidates are.
    "tcga_clinical": ("drug_discovery", "free_public", "in-process:app.tools.tcga_clinical", False, False),
    "recount3_search": ("transcriptomics", "free_public", "in-process:app.tools.recount3_search", False, False),
    "wgcna_modules": ("transcriptomics", "free_public", "in-process:app.tools.wgcna_modules", False, False),
    # docs/12-biotools-triage-shortlist.md's Proteomics cluster
    # (feature/proteomics branch) -- real in-process mass calculation
    # (Pyteomics), no external API. First proteomics coverage in the
    # platform. mokapot (PSM rescoring) investigated and skipped -- it
    # fundamentally needs real search-engine PSM output, which can't be
    # honestly fabricated as a test input.
    "pyteomics_mass": ("proteomics", "free_public", "in-process:app.tools.pyteomics_mass", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1, Proteomics cluster
    # -- real semi-supervised PSM rescoring for FDR control, pairs with
    # pyteomics_mass's peptide mass calculation.
    "mokapot_rescoring": ("proteomics", "free_public", "in-process:app.tools.mokapot_rescoring", False, False),
    # docs/12-biotools-triage-shortlist.md's Phylogenetics cluster
    # (feature/phylogenetics branch) -- this platform's first
    # phylogenetics coverage. Real in-process ML tree inference
    # (piqtree/IQ-TREE) + tree analysis (dendropy), no external API.
    "phylogenetics": ("phylogenetics", "free_public", "in-process:app.tools.phylogenetics", False, False),
    # docs/12-biotools-triage-shortlist.md's Cheminformatics cluster
    # (feature/cheminformatics branch) -- real in-process computation,
    # no external API for the prediction/calculation itself.
    "soltrannet_solubility": ("drug_discovery", "free_public", "in-process:app.tools.soltrannet_solubility", False, False),
    "equilibrator_thermo": ("drug_discovery", "free_public", "in-process:app.tools.equilibrator_thermo", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 2, Cheminformatics
    # cluster. RAscore NOT built -- confirmed live: pins
    # tensorflow-gpu==2.5.0, which no longer exists as an installable
    # distribution on any current platform (only 2.12.0 remains on
    # PyPI, itself since deprecated/merged into plain tensorflow).
    # ToxinPred2 NOT built -- confirmed live: both PyPI releases
    # (1.0, 1.1) crash unconditionally on any real FASTA input via
    # `CM.to_csv(..., sep="\n")`, which Python's own csv module has
    # always rejected ("bad delimiter value") -- a real, reproducible
    # bug in the package's own source, not an environment issue.
    "xtb_quantum": ("drug_discovery", "free_public", "in-process:app.tools.xtb_quantum", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 2 Cheminformatics
    # cluster -- re-investigated after the earlier live-confirmed
    # rejection; the crash is fixable with a single documented source
    # patch (see Dockerfile), not a fork -- confirmed live end-to-end.
    "toxinpred2_toxicity": ("drug_discovery", "free_public", "in-process:app.tools.toxinpred2_toxicity", False, False),
    # docs/17-remaining-tools-wiring-plan.md Phase 1.5 -- local-GPU
    # tools. Both real, confirmed PyPI-installable (`proteinmpnn`
    # requires Python >=3.9,<3.13, satisfied by this image's 3.11;
    # ProtGPT2 has no HF hosted Inference Provider available, confirmed
    # live -- local inference via `transformers` is the only path).
    # GPU used automatically when passed through (docker-compose.gpu.yml,
    # optional), CPU fallback otherwise. RFdiffusion and ChromBPNet NOT
    # built -- see docs/17 for the real, live-confirmed reasons.
    "proteinmpnn_design": ("structural_biology", "free_public", "in-process:app.tools.proteinmpnn_design", False, False),
    "protgpt2_generate": ("structural_biology", "free_public", "in-process:app.tools.protgpt2_generate", False, False),
    "biotransformer_metabolism": ("drug_discovery", "free_public", "in-process:app.tools.biotransformer_metabolism", False, False),
    # Batch virtual screening -- completes the pipeline that was stuck at
    # one-compound-at-a-time (ChEMBL -> Vina -> PLIP). Reuses
    # vina_docking.py's own proven internals rather than the pyscreener
    # package itself (which pulls in ray + openmm, a distributed-compute
    # footprint disproportionate to chat-tool-scale batch docking).
    "virtual_screening": ("drug_discovery", "free_public", "in-process:app.tools.virtual_screening", False, False),
    # OptKnock strain design, built on cobrapy -- completes the
    # metabolic-engineering pipeline (cobra_fba predicts growth,
    # equilibrator_thermo checks feasibility, this proposes the
    # intervention).
    "straindesign_intervention": (
        "systems_biology", "free_public", "in-process:app.tools.straindesign_intervention", False, False,
    ),
    # docs/12-biotools-triage-shortlist.md's Synthetic biology cluster
    # (feature/synthetic-biology branch) -- real in-process combinatorial
    # design (NRP Calculator), no external API. Platform's first
    # synthetic-biology coverage.
    "nrpcalc_design": ("synthetic_biology", "free_public", "in-process:app.tools.nrpcalc_design", False, False),
    # Placeholder only -- no app/tools/drugbank.py, no TOOL_BUILDERS entry.
    # User decision 2026-08-16: wire this once a real DrugBank credential
    # is available; until then this row just marks the intent in the
    # catalog. mcp_server_ref reflects that it's not real yet.
    "drugbank": ("drug_discovery", "commercial_license", "not-yet-implemented", False, True),
    # pharmgkb intentionally not here yet -- see docs/10-build-plan.md
    # Shortlist #6: PharmGKB rebranded to ClinPGx and its old public API
    # surface (api.pharmgkb.org/v1/data/*) no longer resolves/works;
    # every guessed replacement path on clinpgx.org returns the SPA's
    # HTML shell instead of JSON (200 for any path, no clean 404 to
    # signal a wrong guess), so this needs real API docs, not more
    # trial and error.
    # R/Bioconductor bridge (docs/17 Phase 3), file-upload-gated --
    # Mattermost's real file_ids webhook payload is downloaded and
    # classified by app/file_uploads.py, surfaced to the agent only via
    # experiment_uploads' real list_uploaded_files call (no direct
    # prompt injection). Each downstream tool subprocess-calls its own
    # Rscript under app/tools/r_scripts/.
    "experiment_uploads": ("data_infrastructure", "free_public", "in-process:app.tools.experiment_uploads", False, False),
    "dada2_denoise": ("genomics", "free_public", "in-process:app.tools.dada2_denoise", False, False),
    "seurat_analyze": ("transcriptomics", "free_public", "in-process:app.tools.seurat_analyze", False, False),
    "soupx_correct": ("transcriptomics", "free_public", "in-process:app.tools.soupx_correct", False, False),
    "monocle_pseudotime": ("transcriptomics", "free_public", "in-process:app.tools.monocle_pseudotime", False, False),
    "infercnv_analyze": ("transcriptomics", "free_public", "in-process:app.tools.infercnv_analyze", False, False),
    "giotto_spatial": ("transcriptomics", "free_public", "in-process:app.tools.giotto_spatial", False, False),
    "tximport_summarize": ("transcriptomics", "free_public", "in-process:app.tools.tximport_summarize", False, False),
    "sleuth_diffexp": ("transcriptomics", "free_public", "in-process:app.tools.sleuth_diffexp", False, False),
}

# Every tool source with a real builder, i.e. everything except the
# not-yet-implemented placeholders (currently just drugbank) -- this is
# the --tools default (see the module docstring above for why it isn't
# still "pubmed").
ALL_KNOWN_TOOLS = ",".join(
    name for name, entry in KNOWN_TOOL_SOURCES.items() if entry[2] != "not-yet-implemented"
)


async def main(
    team_id: str, bot_user_id: str, bot_token: str, name: str, tool_names: list[str],
    grounding_log_channel_id: str = "",
) -> None:
    async with async_session() as db:
        result = await db.execute(select(Org).where(Org.mattermost_team_id == team_id))
        org = result.scalar_one_or_none()
        if org is None:
            org = Org(
                name="OpenBioLab (dev)", mattermost_team_id=team_id,
                grounding_log_channel_id=grounding_log_channel_id or None,
            )
            db.add(org)
            await db.flush()
            print(f"created org {org.id}")
        else:
            if grounding_log_channel_id and org.grounding_log_channel_id != grounding_log_channel_id:
                org.grounding_log_channel_id = grounding_log_channel_id
                print(f"  updated org.grounding_log_channel_id -> {grounding_log_channel_id}")
            print(f"org already exists: {org.id}")

        result = await db.execute(
            select(Agent).where(Agent.mattermost_bot_user_id == bot_user_id)
        )
        agent = result.scalar_one_or_none()
        encrypted_token = encrypt(bot_token) if bot_token else None
        if agent is None:
            agent = Agent(
                org_id=org.id,
                name=name,
                mattermost_bot_user_id=bot_user_id,
                encrypted_mattermost_bot_token=encrypted_token,
                cluster="master",  # vestigial post-pivot, see 06-data-model.md
                active=True,
            )
            db.add(agent)
            await db.flush()
            print(f"created agent {agent.id} ({name})")
        else:
            agent.name = name
            if encrypted_token:
                agent.encrypted_mattermost_bot_token = encrypted_token
            print(f"agent already exists, updated: {agent.id}")

        for tool_name in tool_names:
            result = await db.execute(select(ToolSource).where(ToolSource.name == tool_name))
            tool_source = result.scalar_one_or_none()
            if tool_name not in KNOWN_TOOL_SOURCES:
                if tool_source is None:
                    print(f"  skipping unknown tool source {tool_name!r} (add it to KNOWN_TOOL_SOURCES)")
                    continue
            else:
                category, access_model, mcp_ref, requires_review, requires_cred = KNOWN_TOOL_SOURCES[tool_name]
                if tool_source is None:
                    tool_source = ToolSource(
                        name=tool_name, category=category, access_model=access_model,
                        requires_credential=requires_cred, mcp_server_ref=mcp_ref,
                        requires_expert_review=requires_review,
                    )
                    db.add(tool_source)
                    await db.flush()
                    print(f"  created tool_source {tool_name!r}")
                elif tool_source.requires_expert_review != requires_review:
                    # Keeps an already-created row in sync with
                    # KNOWN_TOOL_SOURCES if the flag changes later (this is
                    # how clinvar picked up requires_expert_review=True
                    # after being wired before this convention existed).
                    tool_source.requires_expert_review = requires_review
                    print(f"  updated {tool_name!r}.requires_expert_review -> {requires_review}")

            result = await db.execute(
                select(ToolBinding).where(
                    ToolBinding.agent_id == agent.id, ToolBinding.tool_source_id == tool_source.id
                )
            )
            if result.scalar_one_or_none() is None:
                db.add(ToolBinding(agent_id=agent.id, tool_source_id=tool_source.id, binding_type="mcp"))
                print(f"  bound {tool_name!r} to agent")
            else:
                print(f"  {tool_name!r} already bound to agent")

        await db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--bot-user-id", required=True)
    parser.add_argument("--bot-token", default="", help="Mattermost personal access token for this bot")
    parser.add_argument("--name", default="OpenBioLab")
    parser.add_argument(
        "--tools", default=ALL_KNOWN_TOOLS,
        help="Comma-separated tool source names to bind (default: every known real tool source)",
    )
    parser.add_argument(
        "--grounding-log-channel-id", default="",
        help="Mattermost channel ID for the #grounding-log audit channel (FR-10)",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.team_id, args.bot_user_id, args.bot_token, args.name, args.tools.split(","),
            args.grounding_log_channel_id,
        )
    )
