# OpenBioLab

**Open Source for Autonomous Discovery.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](orchestrator/pyproject.toml)
[![Status: build in progress](https://img.shields.io/badge/status-build%20in%20progress-orange)](CHANGELOG.md)

<p align="center">
  <img src="docs/media/capability-demo.gif" alt="OpenBioLab capability demo" width="720">
  <br>
  <sub><a href="docs/media/capability-demo.mp4">full-quality MP4</a> · built HTML to video, via <a href="https://github.com/heygen-com/hyperframes">HyperFrames</a>, real screenshots from a live run</sub>
</p>

## The problem

Modern biology research is spread across dozens of disconnected tools: PubMed for
literature, ChEMBL for compounds, UniProt and PDB for structure, Ensembl for
genomics, ClinVar and gnomAD for variants, KEGG/Reactome/STRING for pathways,
ClinicalTrials.gov and DailyMed for clinical/commercial data — and that's before
counting the 33,000+ specialized tools cataloged in bio.tools. Answering one real
research question ("is this target druggable, and what's already known about it?")
means opening a dozen browser tabs, manually cross-referencing IDs between them,
and trusting your own memory to assemble the answer. AI chatbots don't fix this —
they make it worse, confidently stating biological "facts" with no way to verify
where the claim came from.

## The solution

OpenBioLab is an open-source agentic orchestrator wired to real research tools and
databases, reachable through a single Slack-style chat interface (Mattermost,
self-hosted). Ask a real research question — *"find compounds active against
EGFR"* or *"dock this ligand against 6LU7"* — and the agent plans a methodology,
calls the actual tools needed (18+ live sources today: PubMed, ChEMBL, Open
Targets, Ensembl, UniProt, ClinVar, gnomAD, PDB, AlphaFold, KEGG, Reactome,
STRING, ClinicalTrials.gov, DailyMed, and more), and returns an answer with the
record ID or computation tag behind every claim (`PMID 12345678`, `CHEMBL941`,
`[vina:6LU7]`) — so you can verify it, not just trust it. Nothing is stated that a
tool didn't actually return. Runs local-first, self-hosted, on your own machine or
org infrastructure.

## What you can actually ask it today

These map to tool sources that are wired and live-verified right now, not a roadmap:

| Ask it... |
|---|
| "What compounds are active against EGFR, and what's their mechanism?" |
| "Dock this ligand SMILES against PDB structure 6LU7" |
| "What's the predicted structure of this UniProt protein?" |
| "What's the alpha diversity of this microbiome abundance table?" |
| "Run flux balance analysis on the E. coli core metabolic model" |
| "What clinical trials exist for this drug, and what's on its label?" |
| "What's known about this variant, pathogenicity and population frequency?" |
| "What pathways is this gene involved in?" |
| "Find literature on this topic, including Sci-Hub-available full text where legal" |

## Research workflows this replaces today

Zoomed out past the individual tool table, these are the actual multi-step
research tasks the current tool set already covers end-to-end in one chat message,
without opening a dozen tabs by hand:

- **Target & mechanism research**: go from a gene or protein to its structure, pathways, interaction partners, and known drugs in one pass (Ensembl/UniProt → PDB/AlphaFold → KEGG/Reactome/STRING → Open Targets/ChEMBL).
- **Drug discovery triage**: find active compounds, understand mechanism of action, and run a real molecular docking pose against a target structure, cross-referenced against trial status and label data for anything already approved.
- **Variant interpretation**: pull clinical significance and population allele frequency for the same variant side by side (ClinVar + gnomAD), the two numbers you need together to judge pathogenicity.
- **Literature-grounded due diligence**: search PubMed and get a compliance-checked answer on legal full-text availability (open access vs. Sci-Hub, tier always disclosed), every claim citable back to a PMID or DOI.
- **Systems-level modeling**: real flux balance analysis on a genome-scale metabolic model (an actual constraint-based optimization, not a pathway diagram).
- **Microbiome composition analysis**: real diversity statistics computed locally on your own abundance data, no upload to a third-party service.
- **Regulatory/commercial due diligence**: trial status and drug label lookups in one place, aimed at the commercial/pharma research persona specifically, not just academic literature search.

## How to use it

**Prerequisites:** Docker + Docker Compose v2. That's it — this works the same way
on **Mac, Linux, and Windows** (Docker Desktop on Mac/Windows, Docker Engine on
Linux); every service, including the `claude` CLI itself, runs inside containers,
so nothing OS-specific is required on the host. (The bootstrap script in step 3
needs *some* Python 3.9+ on the host too, but nothing else does.)

**1. Clone and configure**

```bash
git clone https://github.com/RohanV01/AI-BioScientist.git
cd AI-BioScientist
cp .env.example .env        # edit if you want a non-default Postgres password
```

**2. Bring up the stack**

```bash
docker compose up -d
```
Builds the orchestrator image (Node.js + `claude` CLI baked in — first run takes a few minutes) and starts Postgres, Mattermost, and the orchestrator together.

**3. Authenticate the agent** — pick whichever you actually have:
- **Anthropic API key:** set `ANTHROPIC_API_KEY` in `.env`, then `docker compose up -d` again to pick it up. Nothing else to do.
- **Claude subscription (Pro/Max), no API key:** leave `ANTHROPIC_API_KEY` blank and instead run, once:
  ```bash
  docker compose exec orchestrator claude login
  ```
  It prints a URL + code — open it in a browser on any device (doesn't have to be this machine) and approve. Credentials land in the `claude_config` Docker volume and persist across restarts; you won't be asked again unless you `docker compose down -v`.

**4. Bootstrap Mattermost** — creates the admin account, team, bot, and the webhook that wires the agent in (pure Python, same command on every OS, no bash/curl/jq needed):

```bash
python scripts/bootstrap_mattermost.py
```
Prints the generated admin password once (also saved to `.env`). Its final line of output is a ready-to-run `seed_dev_data.py` command with the real `--team-id`/`--bot-user-id`/`--grounding-log-channel-id` values filled in — copy that exact line for the next step.

**5. Seed the agent's tool roster** — run inside the container (there's no host Python venv on a fresh clone):

```bash
docker compose exec orchestrator python scripts/seed_dev_data.py --team-id <...> --bot-user-id <...> --grounding-log-channel-id <...>
```

**6. Restart the orchestrator** to pick up the webhook secret bootstrap just wrote to `.env`:

```bash
docker compose up -d --force-recreate orchestrator
```
⚠️ Don't skip this — if the orchestrator container is still holding the old (or no) secret, `@orchestrator` messages get silently rejected (a 403 that never surfaces in Mattermost's UI at all — the channel just goes quiet). If step 7 below doesn't respond, this is the first thing to check.

**7. Use it**

Go to `http://localhost:8065`, log in with the admin credentials step 4 printed, open `#town-square`, and message `@orchestrator <your question>` to talk to the agent.

**Optional bulk data:** none of the above requires it. If you have (or want to build) a local bibliographic/database corpus, see `data/README.md`. It's gitignored and every agent degrades gracefully without it (`docs/05-ux-behavior.md` §1).

**BYO credentials:** metered tools (like Hugging Face) need your own API key. Add one with `orchestrator/scripts/add_credential.py`; it's encrypted at rest (`orchestrator/app/vault.py`) and never hardcoded to any one account.

## Contributing

Adding a new tool source is a same-day pull request, not a platform project — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Change history

See [`CHANGELOG.md`](CHANGELOG.md).
