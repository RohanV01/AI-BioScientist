# OpenBioLab

**Open Source for Autonomous Discovery.**

OpenBioLab is an open source agentic orchestrator connected to every research tool we can wire in, so you can solve real problems just by chatting on a Slack-style messaging platform (we use Mattermost, a self-hosted, open alternative). Ask a real research question in a chat window, like "find compounds active against EGFR" or "dock this ligand against 6LU7," and get back an answer with a live tool call behind every claim, not a hallucinated guess.

We believe biosciences can be accelerated with AI. This is our attempt at Applied AI in service of that.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](orchestrator/pyproject.toml)
[![Status: build in progress](https://img.shields.io/badge/status-build%20in%20progress-orange)](CHANGELOG.md)

<p align="center">
  <img src="docs/media/capability-demo.gif" alt="OpenBioLab capability demo" width="720">
  <br>
  <sub><a href="docs/media/capability-demo.mp4">full-quality MP4</a> · built HTML to video, via <a href="https://github.com/heygen-com/hyperframes">HyperFrames</a>, real screenshots from a live run</sub>
</p>

## What you can actually ask it today

These map to tool sources that are wired and live-verified right now, not a roadmap:

| Ask it... | 
|---|---|
| "What compounds are active against EGFR, and what's their mechanism?" |
| "Dock this ligand SMILES against PDB structure 6LU7" |
| "What's the predicted structure of this UniProt protein?" |
| "What's the alpha diversity of this microbiome abundance table?" |
| "Run flux balance analysis on the E. coli core metabolic model" |
| "What clinical trials exist for this drug, and what's on its label?" |
| "What's known about this variant, pathogenicity and population frequency?" |
| "What pathways is this gene involved in?" |
| "Find literature on this topic, including Sci-Hub-available full text where legal" |

Every answer comes back with the record ID or computation tag inline (`PMID 12345678`, `CHEMBL941`, `[vina:6LU7]`) so you can verify it against the tool's own output. The agent is instructed to never state a detail a tool didn't actually return, even one it "recognizes."

## Research workflows this replaces today

Zoomed out past the individual tool table, these are the actual multi-step research tasks the current tool set already covers end-to-end in one chat message, without opening a dozen tabs by hand:

- **Target & mechanism research**: go from a gene or protein to its structure, pathways, interaction partners, and known drugs in one pass (Ensembl/UniProt → PDB/AlphaFold → KEGG/Reactome/STRING → Open Targets/ChEMBL).
- **Drug discovery triage**: find active compounds, understand mechanism of action, and run a real molecular docking pose against a target structure, cross-referenced against trial status and label data for anything already approved.
- **Variant interpretation**: pull clinical significance and population allele frequency for the same variant side by side (ClinVar + gnomAD), the two numbers you need together to judge pathogenicity.
- **Literature-grounded due diligence**: search PubMed and get a compliance-checked answer on legal full-text availability (open access vs. Sci-Hub, tier always disclosed), every claim citable back to a PMID or DOI.
- **Systems-level modeling**: real flux balance analysis on a genome-scale metabolic model (an actual constraint-based optimization, not a pathway diagram).
- **Microbiome composition analysis**: real diversity statistics computed locally on your own abundance data, no upload to a third-party service.
- **Regulatory/commercial due diligence**: trial status and drug label lookups in one place, aimed at the commercial/pharma research persona specifically, not just academic literature search.

## Getting started

**Prerequisites:** Docker + Docker Compose v2, Python 3.11+.

```bash
git clone https://github.com/RohanV01/AI-BioScientist.git
cd AI-BioScientist
cp .env.example .env        # edit if you want a non-default Postgres password
docker compose up -d postgres
# wait for postgres to report healthy, then:
docker compose up -d mattermost
```

Mattermost is reachable at `http://localhost:8065`; first visit creates the initial admin account. Bring up the Orchestrator Service (`orchestrator/`) per `docs/10-build-plan.md` to wire the agent in.

**Optional bulk data:** none of the above requires it. If you have (or want to build) a local bibliographic/database corpus, see `data/README.md`. It's gitignored and every agent degrades gracefully without it (`docs/05-ux-behavior.md` §1).

**BYO credentials:** metered tools (like Hugging Face) need your own API key. Add one with `orchestrator/scripts/add_credential.py`; it's encrypted at rest (`orchestrator/app/vault.py`) and never hardcoded to any one account.

## Change history

See [`CHANGELOG.md`](CHANGELOG.md).
