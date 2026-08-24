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

**Prerequisites:** Docker + Docker Compose v2. That's it — this works the same way on **Mac, Linux, and Windows** (Docker Desktop on Mac/Windows, Docker Engine on Linux); every service, including the `claude` CLI itself, runs inside containers, so nothing OS-specific is required on the host. (The bootstrap script in step 3 needs *some* Python 3.9+ on the host too, but nothing else does.)

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
  docker compose exec -it orchestrator claude auth login
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

**Optional: full-text paper downloads.** `download_paper` (`orchestrator/app/tools/literature_discovery.py`) uses the [Camofox stealth browser](https://github.com/jo-inc/camofox-browser) to actually fetch PDFs -- optional and independently configured in `.env`; without it set, discovery/citation still works, downloading full-text PDFs just doesn't. It drives the real Sci-Hub UI (paste the DOI, click open, click the page's own save button) and captures the resulting browser download, so it needs no API keys or scraping workarounds beyond a running Camofox server:
1. `git clone https://github.com/jo-inc/camofox-browser external/camofox-browser` (gitignored -- a local dependency clone, not vendored into this repo's history).
2. `cd external/camofox-browser && npm install && npm start` -- first run downloads the Camoufox browser + GeoIP database (~300MB, a few minutes). Runs on `http://localhost:9377` by default.
3. Set `CAMOFOX_API_URL=http://localhost:9377` (and `CAMOFOX_ACCESS_KEY` only if that deployment requires auth) plus `SCIHUB_MIRROR_URLS` (comma-separated Sci-Hub mirrors; list every one you know is currently working, since mirrors go down/get blocked independently) in `.env`.

Every download is checked against the paper's own expected title/DOI (`_verify_pdf_content` in `literature_discovery.py`) before anything downstream trusts it -- a real browser download can succeed end-to-end while a Sci-Hub mirror quietly serves the wrong paper's PDF for a given DOI (seen live during testing). A flagged mismatch is reported in `download_paper`'s own result text, and `read_paper` refuses to extract "findings" from a file flagged that way.

**Research experiments.** Every research investigation gets its own folder (`data/Experiments/<id>/`) and DB row -- control it with the `/experiment` Slash Command (`start ["name"]` / `end` / `status` / `conclude`), or just message `@orchestrator` and one opens automatically. Register the command once per Mattermost instance:
```
curl -X POST http://localhost:8065/api/v4/commands \
  -H "Authorization: Bearer <your admin session token>" -H 'Content-Type: application/json' \
  -d '{"team_id": "<your team id>", "trigger": "experiment", "method": "P",
       "url": "<your orchestrator URL>/webhooks/mattermost/experiment",
       "auto_complete": true, "display_name": "Experiment",
       "description": "Controls the current research experiment for this channel"}'
```
Copy the response's own `token` field into `.env` as `MATTERMOST_EXPERIMENT_COMMAND_SECRET` (a separate value from `MATTERMOST_WEBHOOK_SECRET` -- Mattermost auto-generates one token per integration, no way to set a custom one).

`read_paper`'s structured extraction and `/experiment conclude`'s synthesis run through a modular one-shot LLM backend (`orchestrator/app/llm_backend.py`), not tied to any single provider: it tries a real Anthropic API key (`ANTHROPIC_API_KEY`), then a local [LM Studio](https://lmstudio.ai) server (`LM_STUDIO_BASE_URL`), then falls back to the `claude` CLI's own subscription login from step 5 above -- so both features work with zero extra setup if you already logged in there. Set `LLM_BACKEND` in `.env` to pin one explicitly instead of the default `auto` fallback chain.

## Change history

See [`CHANGELOG.md`](CHANGELOG.md).
