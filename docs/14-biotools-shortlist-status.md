# Biotools Shortlist — Live Status (as of 2026-08-24, updated 2026-08-25)

Cross-check of `12-biotools-triage-shortlist.md` against actual code state.
Every row in that file is still marked `[ ]` (not yet built) — the checkbox
markers in that doc were never updated. This file corrects that by checking
the real source of truth instead: `orchestrator/app/tool_roster.py`'s
`TOOL_BUILDERS` registry (what the agent can actually call), whether each
tool has a builder file under `orchestrator/app/tools/`, whether it's seeded
in `scripts/seed_dev_data.py`, and whether `docs/13-test-report.md`'s E2E
combo runs exercise it.

**Method:** read `12-biotools-triage-shortlist.md`, read `tool_roster.py`
(`TOOL_BUILDERS` dict, lines 73–176), confirmed each has a file in
`orchestrator/app/tools/`, a unit test in `orchestrator/tests/`, and a seed
entry, then cross-referenced `13-test-report.md`'s 10 E2E combo rows for
live pass/fail confirmation.

## Live now (16 tools, all wired + unit-tested + E2E-passing)

| Shortlist name | Registered as (tool_roster.py) | E2E combo confirming it |
|---|---|---|
| eQuilibrator | `equilibrator_thermo` | #6 Metabolic engineering |
| GSEApy | `gene_set_enrichment` | #10 Enrichment & annotation |
| g:Profiler / gprofiler-official | `gprofiler_enrichment` | #10 Enrichment & annotation |
| MHCflurry | `mhcflurry_binding` | #8 Immunoinformatics / epitope design |
| msprime | `msprime` | #7 Comparative genomics / phylogenetics |
| nrpcalc | `nrpcalc_design` | (unit-tested, no E2E combo yet) |
| IQ-TREE/ete3/DendroPy cluster | `phylogenetics` | #7 Comparative genomics / phylogenetics |
| PLIP | `plip_interactions` | #4 Structure-based drug design, #5 virtual screening funnel |
| Primer3 / primer3-py | `primer3` | #8 Immunoinformatics / epitope design |
| HMMER3 / pyhmmer | `pyhmmer_search` | #8 Immunoinformatics / epitope design |
| Pyteomics | `pyteomics_mass` | #9 Proteomics mass-spec workflow |
| SolTranNet | `soltrannet_solubility` | #5 Target-to-lead virtual screening funnel |
| sourmash | `sourmash_compare` | #7 Comparative genomics / phylogenetics |
| straindesign | `straindesign_intervention` | #6 Metabolic engineering |
| pyscreener | `virtual_screening` | #5 Target-to-lead virtual screening funnel |
| Clustal Omega/MAFFT (partial, MAFFT only) | `msa` | #7 Comparative genomics / phylogenetics (added 2026-08-24 to close the "no MSA tool" gap found by battle-testing, see `15-battle-test-report.md` Gap 5) |

All 16 have: a builder file in `orchestrator/app/tools/`, an entry in
`TOOL_BUILDERS` in `tool_roster.py`, a dedicated unit test in
`orchestrator/tests/`, and a seed row in `scripts/seed_dev_data.py` (so
they're actually bound to the agent, not just dead code). Per
`13-test-report.md`, all 10 E2E combo tests pass as of the `test-and-fix`
branch's last run — one caveat noted there: combo #4/#5 found and fixed a
real bug in `plip_interactions`, since resolved.

## Not live — everything else in the shortlist

Every other tool in `12-biotools-triage-shortlist.md` (Fpocket, US-align,
DockQ/spyrmsd, Foldseek/FoldMason, DSSP, IDPConformerGenerator,
correlationplus, HADDOCK3, BLAST+, DIAMOND, Clustal Omega (MAFFT itself is
now live via `msa`, see above), EMBOSS,
Minimap2/mappy, Prodigal, MUMmer4, PhyKIT/BioKIT, OrthoFinder, PAML,
ASTRAL-Pro2, SCANPY, Enrichr, clusterProfiler, pyComBat, scVelo, rMATS,
WGCNA/PyWGCNA, SCENIC, VIPER, HunFlair, OmniPath, BUSCO, pixy, poolfstat,
egglib, ADMIXTURE/Eigensoft, TreeMix, selscan, LDSC, pandasGWAS, sourmash's
metagenomics siblings (Kraken2, Kaiju, MetaPhlAn, HUMAnN, Prokka/Bakta,
AMRFinderPlus, CheckM2/CheckV, eggNOG-mapper, FastANI, GTDB-Tk, dada2,
Barrnap), LightDock, Auto3D, AiZynthFinder, Chemprop, BioTransformer/
Pickaxe, RAscore, ToxinPred2, xtb, libRoadRunner/basico, ANARCI, AbLang,
BioPhi, PyIR, clusTCR/tcrdist3, mokapot, Comet/Sage, DIA-NN, bebop/poly,
OpenCloning, PEGG, cptac, pyBioPortal, DDGun, bio-firewall) has **no
builder file, no `TOOL_BUILDERS` entry, and no seed row** — confirmed absent
from `orchestrator/app/tools/`. None of these are live.

## Bottom line

- **Live: 16 / ~115** shortlisted tools (roughly 14%), all from this one
  triage pass, built and validated after the shortlist doc itself was
  written and never checked off in it.
- **Not live: the rest** — including every DATA-gated tool (needs
  FASTQ/BAM/VCF/scRNA-seq input the platform doesn't ingest yet), every
  R/Bioconductor-only candidate (blocked on an `rpy2`/`Rscript` bridge
  that doesn't exist), and every GPU-heavy model (explicitly deferred to
  Phase 6).
- Action item for whoever owns `12-biotools-triage-shortlist.md`: flip the
  15 checkboxes above to `[x]` with a pointer to this file or to
  `13-test-report.md`, so the doc stops understating what's built.
