# AI Scientist

**Open Source for Autonomous Discovery.**

Ask a real research question in a chat window — "find compounds active against EGFR," "dock this ligand against 6LU7," "what's the alpha diversity of this microbiome sample" — and get back an answer with a live tool call behind every claim, not a hallucinated guess. AI Scientist is a local-first research platform: a Mattermost workspace where you delegate to a Claude-powered agent wired to 20+ real bio/chem databases and computation tools, instead of manually stitching together a dozen browser tabs by hand.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](orchestrator/pyproject.toml)
[![Status: build in progress](https://img.shields.io/badge/status-build%20in%20progress-orange)](CHANGELOG.md)

> A capability-demo video is in progress (built HTML → video, via HyperFrames) and will be embedded here once it's rendered.

## Why this exists

Real research tooling is scattered — paywalled APIs, single-paper GitHub repos nobody maintains, databases that need an institutional login, and a paid tool locked to whoever's credit card is on file. AI Scientist is built so that (a) every answer is traceable back to the exact tool call and record that produced it, (b) any org can bring their own credential for a metered tool instead of it being hardcoded to one person's account, and (c) adding a new tool is a same-day pull request — one file, three one-line registrations — not a platform rewrite. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for exactly how that works and a 100+-item backlog of triaged tools ready to build, organized into parallel branches anyone can pick up.

## What you can actually ask it today

These map to tool sources that are wired and live-verified right now, not a roadmap:

| Ask it... | It calls... |
|---|---|
| "What compounds are active against EGFR, and what's their mechanism?" | ChEMBL + Open Targets |
| "Dock this ligand SMILES against PDB structure 6LU7" | AutoDock Vina (real docking, real binding poses) |
| "What's the predicted structure of this UniProt protein?" | AlphaFold DB + UniProt |
| "What's the alpha diversity of this microbiome abundance table?" | scikit-bio (real local computation) |
| "Run flux balance analysis on the E. coli core metabolic model" | cobrapy + the BiGG model database |
| "What clinical trials exist for this drug, and what's on its label?" | ClinicalTrials.gov + DailyMed |
| "What's known about this variant — pathogenicity and population frequency?" | ClinVar + gnomAD |
| "What pathways is this gene involved in?" | KEGG + Reactome + STRING |
| "Find literature on this topic, including Sci-Hub-available full text where legal" | PubMed + a compliance-checked literature-discovery tool |

Every answer comes back with the record ID or computation tag inline (`PMID 12345678`, `CHEMBL941`, `[vina:6LU7]`) so you can verify it against the tool's own output — the agent is instructed to never state a detail a tool didn't actually return, even one it "recognizes."

## Tool & data-source coverage

21 tool sources wired end-to-end (20 live today with no setup beyond cloning; 1 pending a free API token), plus one cataloged placeholder waiting on a licensed data source:

| Domain | Sources | Status |
|---|---|---|
| Literature | PubMed, literature discovery (Sci-Hub availability, compliance-checked) | ✅ live |
| Drug discovery | ChEMBL, Open Targets, AutoDock Vina (real molecular docking) | ✅ live |
| Genomics | Ensembl, UniProt, ClinVar, gnomAD | ✅ live |
| Structural biology | RCSB PDB, AlphaFold DB, BioPandas (structure composition) | ✅ live |
| Systems biology | KEGG, Reactome, STRING, cobrapy (flux balance analysis) | ✅ live |
| Clinical / commercial | ClinicalTrials.gov, DailyMed | ✅ live |
| Ontologies | OLS (disease/phenotype/GO term search) | ✅ live |
| Microbiome | scikit-bio (alpha diversity) | ✅ live |
| Compute / ML | Hugging Face (ESM2 protein-sequence inference) | 🔑 wired, needs your own free HF token ([`scripts/add_credential.py`](orchestrator/scripts/add_credential.py)) |
| Drug discovery (licensed data) | DrugBank | 📋 cataloged placeholder — needs a licensed credential, not yet implemented |

**Structural biology, drug discovery, and systems biology tools run real local computation** — AutoDock Vina, cobrapy, scikit-bio, and BioPandas execute the actual packages inside the orchestrator's own Python environment, with no external API call and no rate limit for the computation itself.

## What's next — the open backlog

`docs/12-biotools-triage-shortlist.md` has **100+ additional tools already triaged**, one-by-one, across a 33,888-entry bio.tools catalog and 1,000 starred GitHub repos — each tagged with what gap it fills, whether it's a `pip install` away or needs a real integration, and how confident the triage is. They're organized into 11 capability clusters (structural biology, sequence analysis, phylogenetics, transcriptomics, population genetics, metagenomics, cheminformatics, immunoinformatics, proteomics, synthetic biology, and more), each with its own branch so parallel work doesn't collide. The single highest-leverage open item: an R/Bioconductor bridge that unlocks a large cluster of the strongest remaining candidates (Seurat, scran, dada2, WGCNA). See [`CONTRIBUTING.md`](CONTRIBUTING.md).

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

Mattermost is reachable at `http://localhost:8065` — first visit creates the initial admin account. Bring up the Orchestrator Service (`orchestrator/`) per `docs/10-build-plan.md` to wire the agent in.

**Optional bulk data:** none of the above requires it. If you have (or want to build) a local bibliographic/database corpus, see `data/README.md` — it's gitignored and every agent degrades gracefully without it (`docs/05-ux-behavior.md` §1).

**BYO credentials:** for any tool marked 🔑 above, add your own key with `orchestrator/scripts/add_credential.py` — it's encrypted at rest (`orchestrator/app/vault.py`) and never hardcoded to any one account.

## Architecture, in brief

Mattermost (messaging) → FastAPI Orchestrator (webhook handling, tool roster assembly, grounding/citation extraction) → Claude Agent SDK master agent (Plan → Execute → Synthesize loop) → MCP-wired tools (external API calls or real local computation). One agent, one dynamically-assembled tool roster built from database `TOOL_BINDING` rows — not one hardcoded function per domain. Full rationale in [`docs/07-system-architecture.md`](docs/07-system-architecture.md); the phased build plan is in [`docs/10-build-plan.md`](docs/10-build-plan.md).

`reference/rxdis-legacy/` holds design docs from RxDis, a prior drug-discovery pipeline this project wraps as an agent rather than rebuilding — see `docs/10-build-plan.md` Phase 2.

## Reading order

1. `docs/01-project-goals.md` — what and why
2. `docs/02-prd.md` — scope
3. `docs/03-user-personas.md` — who this is for
4. `docs/04-information-architecture.md` — how the Mattermost workspace is organized
5. `docs/05-ux-behavior.md` — how it behaves
6. `docs/06-data-model.md` — the schema
7. `docs/07-system-architecture.md` — how the pieces fit together
8. `docs/08-cross-feature-journeys.md` — end-to-end scenarios
9. `docs/09-test-strategy-acceptance-criteria.md` — how we know it works
10. `docs/10-build-plan.md` — the phased roadmap (start here for "what's next")
11. `docs/11-backlog-traceability.md` — full status of every experiment/flagship/gap/paid-tool from the original research report against these phases
12. `docs/12-biotools-triage-shortlist.md` — the 100+-item open tool backlog (start here to contribute)

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) — adding a tool is one file and three one-line registrations. The backlog is large, triaged, and split into parallel branches on purpose: pick a cluster, build something real, open a PR.

## Change history

See [`CHANGELOG.md`](CHANGELOG.md).
