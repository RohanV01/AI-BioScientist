# OpenBioLab

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](orchestrator/pyproject.toml)
[![Status: build in progress](https://img.shields.io/badge/status-build%20in%20progress-orange)](CHANGELOG.md)

<p align="center">
  <img src="docs/media/capability-demo.gif" alt="OpenBioLab capability demo" width="720">
</p>

OpenBioLab is an open-source research assistant for biology and drug discovery. You ask it a question in a chat window, and it runs real scientific tools and databases to answer it, instead of just generating text from memory.

It is free, self-hosted, and open source (MIT license). You run it on your own computer or server, with your own data staying private.

## What it does

- Answers research questions by actually querying real scientific databases and running real calculations, not guessing.
- Every answer says exactly where it came from: which tool or database produced it, or if it's the model's own reasoning rather than a database result.
- Can run multi-step research tasks on its own: look something up, use the result to run a second tool, and summarize the findings.
- Covers over 100 tools today, including literature search, drug and compound data, protein structure lookup, genetic variant lookup, docking simulations, and more.

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

- **Runs on your machine.** Your questions and data don't have to leave your own computer or server.
- **Every claim is checkable.** The system won't label something as fact-backed unless it's tied to a real tool result.
- **Not locked to one AI provider.** Works with a Claude subscription or an API key — no separate paywall just to use it.
- **Open to new tools.** Adding a new database or tool follows one documented pattern (see `CONTRIBUTING.md`), so the tool list keeps growing.

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

OpenBioLab connects existing tools and databases together — it doesn't reimplement them.

- **Platform:** [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python), [Mattermost](https://mattermost.com), [Camofox](https://github.com/jo-inc/camofox-browser), [LM Studio](https://lmstudio.ai) (optional)
- **Databases:** [PubMed](https://pubmed.ncbi.nlm.nih.gov)/[OpenAlex](https://openalex.org), [ChEMBL](https://www.ebi.ac.uk/chembl/), [Open Targets](https://platform.opentargets.org), [UniProt](https://www.uniprot.org), [PDB](https://www.rcsb.org), [AlphaFold DB](https://alphafold.ebi.ac.uk), [Ensembl](https://www.ensembl.org), [ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/), [gnomAD](https://gnomad.broadinstitute.org), [KEGG](https://www.genome.jp/kegg/), [Reactome](https://reactome.org), [STRING](https://string-db.org), [ClinicalTrials.gov](https://clinicaltrials.gov), [DailyMed](https://dailymed.nlm.nih.gov)
- **Calculations:** [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina) (docking), [COBRApy](https://opencobra.github.io/cobrapy/) (metabolic modeling), [scikit-bio](http://scikit-bio.org), [BioPandas](http://rasbt.github.io/biopandas/), [MAFFT](https://mafft.cbrc.jp/alignment/software/) (sequence alignment)

## Project history

See [`CHANGELOG.md`](CHANGELOG.md) for a full log of what's been built and when.
