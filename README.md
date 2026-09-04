# OpenBioLab

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](orchestrator/pyproject.toml)
[![Status: build in progress](https://img.shields.io/badge/status-build%20in%20progress-orange)](CHANGELOG.md)

<p align="center">
  <img src="docs/media/capability-demo.gif" alt="OpenBioLab capability demo" width="720">
</p>

OpenBioLab is an open-source research assistant for biology and drug discovery. You ask it a question in a chat window, and it runs real scientific tools and databases to answer it, instead of just generating text from memory.

It is free, self-hosted, and open source (MIT license). Frontier-grade AI research tooling has mostly shown up behind a paywall or a closed platform — OpenBioLab exists so a grad student, an independent lab, or a researcher anywhere can run the same class of tooling themselves, extend it, and build on it, without waiting on a vendor's roadmap.

## What it does

- Answers research questions by actually querying real scientific databases and running real calculations, not guessing.
- Every answer says exactly where it came from: which tool or database produced it, or if it's the model's own reasoning rather than a database result.
- Can run multi-step research tasks on its own: look something up, use the result to run a second tool, and summarize the findings.
- Covers 115 tools today, including literature search, drug and compound data, protein structure lookup, genetic variant lookup, docking simulations, and more.

## Example uses

- Research a drug target and its known mechanism
- Screen candidate compounds for a disease
- Look up what's known about a genetic variant
- Search and summarize scientific literature with citations
- Model a biological pathway or metabolic network
- Pull together background for regulatory or commercial due diligence

## How it works

1. You type a question into a chat app called [Mattermost](https://mattermost.com) (an open-source alternative to Slack, included in this project).
2. An AI agent reads your question and decides which tools it needs.
3. It runs those tools against real databases and calculations, not from memory.
4. It writes an answer and labels every claim in it: backed by a real result, its own reasoning, or something it couldn't verify.
5. The full trail — which tools ran and what they returned — is saved and viewable, so any answer can be checked.

## Why it's built this way

- **Open infrastructure accelerates research.** Self-hosted and MIT-licensed means any lab can run it, fork it, and extend it — the point is to widen access to real research tooling, not gate it behind a subscription tier.
- **Every claim is checkable.** The system won't label something as fact-backed unless it's tied to a real tool result, so results are trustworthy enough to actually build on.
- **Not locked to one AI provider.** Works with a Claude subscription or an API key — no separate paywall just to use it.
- **Open to new tools.** Adding a new database or tool follows one documented pattern (see `CONTRIBUTING.md`), so the tool list keeps growing as the community adds to it.

## Getting started

**You need:** Docker and Docker Compose. That's it — it works the same on Mac, Linux, and Windows, since everything runs inside containers.

**1. Get the code and set it up**

```bash
git clone https://github.com/RohanV01/AI-BioScientist.git
cd AI-BioScientist
cp .env.example .env
```

Generate two passwords and add them to `.env` (the example file ships with placeholders — fine for a quick local test, not safe if anyone else can reach this machine):

```bash
# For POSTGRES_PASSWORD
openssl rand -base64 24

# For CREDENTIAL_VAULT_KEY (only needed if you plan to connect paid tools later)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep a backup of `CREDENTIAL_VAULT_KEY` somewhere safe — if it's lost, any credentials you've stored can't be recovered.

**2. Start everything**

```bash
docker compose up -d
```

This builds and starts the chat app, database, and the AI agent together. The first run takes a few minutes.

**3. Connect your Claude account** — pick one:

- **Using an API key:** add `ANTHROPIC_API_KEY` to `.env`, then run `docker compose up -d` again.
- **Using a Claude subscription (Pro/Max), no API key:** run this once and follow the printed link:
  ```bash
  docker compose exec -it orchestrator claude auth login
  ```
  Your login is saved and won't be needed again unless you fully reset the project.

**4. Set up the chat app**

```bash
python scripts/bootstrap_mattermost.py
```

This creates your admin account and prints a password (also saved to `.env`), plus a ready-to-run command for the next step — copy it exactly.

**5. Turn on the tools**

Run the command printed by the previous step, for example:

```bash
docker compose exec orchestrator python scripts/seed_dev_data.py --team-id <...> --bot-user-id <...> --bot-token <...> --grounding-log-channel-id <...>
```

**6. Restart once more** to apply the last setting:

```bash
docker compose up -d --force-recreate orchestrator
```

**7. Start using it**

Go to `http://localhost:8065`, log in with the admin account from step 4, and message `@orchestrator` with any research question.

### Optional

- **Bulk local databases:** not required to get started. See `data/README.md` if you want to add a local literature/database corpus later — everything works fine without it.
- **GPU support:** not required either. A couple of tools run faster with an NVIDIA GPU; see `docker-compose.gpu.yml` if you have one.
- **Your own API keys for paid tools:** add them with `orchestrator/scripts/add_credential.py`. They're stored encrypted, never shared.
- **Full paper downloads:** works out of the box for open-access papers. For paywalled papers, it uses a built-in browser tool and clearly labels the source of every download.
- **Research sessions:** each investigation is automatically saved to its own folder and can be started, ended, or reviewed with the `/experiment` command. One-time setup instructions are in `docs/`.

If anything doesn't respond after setup, check the logs first:

```bash
docker compose logs orchestrator
```

## Contributing

New tools, new workflows, and bug reports are all welcome. `CONTRIBUTING.md` walks through exactly how to add a new scientific tool — that's the most useful way to help.

## Built on

OpenBioLab connects existing open tools and databases together — it doesn't reimplement them. Every one of the 115 tool sources wired in today is credited below, organized by category to match how the codebase itself is organized (`orchestrator/app/tools/`).

- **Platform:** [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python), [Mattermost](https://mattermost.com), [Camofox](https://github.com/jo-inc/camofox-browser), [LM Studio](https://lmstudio.ai) (optional), [Hugging Face](https://huggingface.co) (BYO-credential model hosting)

- **Literature & clinical/regulatory:** [PubMed](https://pubmed.ncbi.nlm.nih.gov)/[OpenAlex](https://openalex.org), [Europe PMC](https://europepmc.org), [Retraction Watch](https://retractionwatch.com), [ClinicalTrials.gov](https://clinicaltrials.gov), [DailyMed](https://dailymed.nlm.nih.gov), [openFDA](https://open.fda.gov), [ClinPGx](https://www.clinpgx.org) (formerly PharmGKB)

- **Genomics, variants & population genetics:** [Ensembl](https://www.ensembl.org) + Ensembl VEP, [UniProt](https://www.uniprot.org), [ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/), [gnomAD](https://gnomad.broadinstitute.org), [GWAS Catalog](https://www.ebi.ac.uk/gwas/), [Human Phenotype Ontology](https://hpo.jax.org), [EBI Ontology Lookup Service](https://www.ebi.ac.uk/ols4) (Gene Ontology, MONDO, NCBI Taxonomy, and more), [ADMIXTURE](https://dalexander.github.io/admixture/), [EIGENSOFT](https://github.com/DReichLab/EIG), [EggLib](https://egglib.org), [LDSC](https://github.com/bulik/ldsc) (LD Score Regression), [msprime](https://tskit.dev/msprime/), [pixy](https://pixy.readthedocs.io), [poolfstat](https://cran.r-project.org/package=poolfstat), [selscan](https://github.com/szpiech/selscan), [TreeMix](https://bitbucket.org/nygcresearch/treemix), [cBioPortal](https://www.cbioportal.org), [TCGA](https://www.cancer.gov/tcga) clinical data, [OmniPath](https://omnipathdb.org)

- **Pathways & interactions:** [KEGG](https://www.genome.jp/kegg/), [Reactome](https://reactome.org), [STRING](https://string-db.org)

- **Structural biology:** [AlphaFold DB](https://alphafold.ebi.ac.uk), [RCSB PDB](https://www.rcsb.org), [DSSP](https://swift.cmbi.umcn.nl/gv/dssp/), [Foldseek](https://github.com/steineggerlab/foldseek), [FoldMason](https://github.com/steineggerlab/foldmason), [US-align](https://zhanggroup.org/US-align/), [Fpocket](https://github.com/Discngine/fpocket), [PLIP](https://github.com/pharmai/plip) (protein-ligand interaction profiler), [spyrmsd](https://github.com/RMeli/spyrmsd), [ProteinMPNN](https://github.com/dauparas/ProteinMPNN), [ProtGPT2](https://huggingface.co/nferruz/ProtGPT2), [AbLang](https://github.com/oxpig/AbLang), [ANARCI](https://github.com/oxpig/ANARCI) (antibody numbering), [correlationplus](https://github.com/tekpinar/correlationplus)

- **Phylogenetics:** [IQ-TREE](http://www.iqtree.org)/piqtree, [PhyKIT](https://github.com/JLSteenwyk/PhyKIT), [ASTRAL-Pro](https://github.com/chaoszhang/ASTER), [FastTree](http://www.microbesonline.org/fasttree/), [OrthoFinder](https://github.com/davidemms/OrthoFinder), [PAML](http://abacus.gene.ucl.ac.uk/software/paml.html) (yn00)

- **Sequence alignment & search:** [BLAST](https://blast.ncbi.nlm.nih.gov), [DIAMOND](https://github.com/bbuchfink/diamond), [minimap2](https://github.com/lh3/minimap2), [MUMmer4](https://github.com/mummer4/mummer), [Clustal Omega](http://www.clustal.org/omega/), [EMBOSS](https://emboss.sourceforge.net) (Water), [MAFFT](https://mafft.cbrc.jp/alignment/software/), [PyHMMER](https://github.com/althonos/pyhmmer), [sourmash](https://sourmash.readthedocs.io), [Primer3](https://primer3.org)

- **Metagenomics & microbial genomics:** [Kraken2](https://ccb.jhu.edu/software/kraken2/), [Kaiju](https://kaiju.binf.ku.dk), [Prokka](https://github.com/tseemann/prokka), [Bakta](https://github.com/oschwengers/bakta), [AMRFinderPlus](https://github.com/ncbi/amr), [CheckM2](https://github.com/chklovski/CheckM2), [CheckV](https://bitbucket.org/berkeleylab/checkv), [FastANI](https://github.com/ParBLiSS/FastANI), [Barrnap](https://github.com/tseemann/barrnap), [Prodigal](https://github.com/hyattpd/Prodigal), [DADA2](https://benjjneb.github.io/dada2/)

- **Cheminformatics & drug discovery:** [ChEMBL](https://www.ebi.ac.uk/chembl/), [PubChem](https://pubchem.ncbi.nlm.nih.gov), [Open Targets](https://platform.opentargets.org), [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina) (docking + virtual screening), [LightDock](https://github.com/lightdock/lightdock), [xtb](https://github.com/grimme-lab/xtb) (semiempirical quantum chemistry), [Auto3D](https://github.com/isayevlab/Auto3D_seqm), [NRPCalc](https://github.com/vishalsimran/nrpcalc) (non-ribosomal peptide design), [DNA Chisel](https://github.com/Edinburgh-Genome-Foundry/DnaChisel), [pydna](https://github.com/BjornFJohansson/pydna) (Gibson assembly simulation), [SolTranNet](https://github.com/gnina/SolTranNet) (solubility prediction), [ToxinPred2](https://webs.iiitd.edu.in/raghava/toxinpred2/), [BioTransformer](https://biotransformer.ca) (metabolism prediction), [eQuilibrator](https://equilibrator.weizmann.ac.il) (thermodynamics), [libRoadRunner](https://libroadrunner.org) (kinetic simulation), [Mokapot](https://mokapot.readthedocs.io) (proteomics rescoring), [Pyteomics](https://pyteomics.readthedocs.io)

- **Transcriptomics & single-cell:** [Scanpy](https://scanpy.readthedocs.io), [Seurat](https://satijalab.org/seurat/), [SoupX](https://github.com/constantAmateur/SoupX), [Monocle3](https://cole-trapnell-lab.github.io/monocle3/), [inferCNV](https://github.com/broadinstitute/infercnv), [Giotto](https://giottosuite.readthedocs.io) (spatial transcriptomics), [pyComBat](https://epigenelabs.github.io/pyComBat/), [clusterProfiler](https://guangchuangyu.github.io/software/clusterProfiler/), [GSEApy](https://gseapy.readthedocs.io)/[Enrichr](https://maayanlab.cloud/Enrichr/), [g:Profiler](https://biit.cs.ut.ee/gprofiler/), [WGCNA](https://cran.r-project.org/package=WGCNA), [Sleuth](https://pachterlab.github.io/sleuth/), [tximport](https://bioconductor.org/packages/tximport/), [recount3](https://rna.recount.bio/)

- **Immunoinformatics:** [MHCflurry](https://github.com/openvax/mhcflurry), [epitopepredict](https://github.com/dmnfarrell/epitopepredict), [PyIR](https://github.com/crowelab/PyIR) (IgBLAST V(D)J assignment), [TCRdist3](https://tcrdist3.readthedocs.io), [HunFlair](https://github.com/flairNLP/flair) (biomedical NER)

- **Metabolic modeling:** [COBRApy](https://opencobra.github.io/cobrapy/) (flux balance analysis), [StrainDesign](https://github.com/klamt-lab/straindesign)

- **General:** [scikit-bio](http://scikit-bio.org), [BioPandas](http://rasbt.github.io/biopandas/) (structure parsing)

## Project history

See [`CHANGELOG.md`](CHANGELOG.md) for a full log of what's been built and when.
