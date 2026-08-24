# OpenBioLab

**Open source. Open science. A real intelligence, wired to real scientific tools, running real experiments.**

At its core, OpenBioLab is one idea: connect an LLM to actual scientific tools — the same databases, structure predictors, docking engines, and simulators a working researcher already uses — and let it run genuine autonomous experiments, not just answer questions about them. Every step is a real tool call against a real result, chained into the kind of multi-step investigation that used to mean a dozen open tabs and an afternoon: gene → structure → pathway → known drugs, in one message.

It's fully open source (MIT) on purpose. Frontier AI-agent tooling for science has mostly shown up behind a paywall, inside one company's walled garden, or as a demo you can't actually run. OpenBioLab is the opposite bet: self-hostable by anyone, extensible by anyone, and free of any single vendor's lock-in — because democratizing serious scientific discovery means the tool that does it has to be something a grad student, an independent lab, or a researcher anywhere in the world can actually stand up themselves, not just something they read about. Open science needs open infrastructure; this is an attempt at that infrastructure.

Ask it a real research question in a chat window — "find compounds active against EGFR" or "dock this ligand against 6LU7" — and get back an answer with a live tool call behind every claim, not a hallucinated guess. Every response is `grounded` (backed by at least one real tool citation), `synthesis` (reasoning over grounded results, labeled as such), or `ungroundable` (the tools couldn't answer it, and it says so) — there's no fourth option where the model just states something it "recognizes."

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

Every answer comes back with the record ID or computation tag inline (`PMID 12345678`, `CHEMBL941`, `[vina:6LU7]`) so you can verify it against the tool's own output.

## Research workflows this replaces today

This is what "connecting an intelligence to real scientific tools" actually looks like end to end: not one lookup, but a chained, multi-step investigation the agent runs autonomously in a single message, the same way a researcher would move between tools by hand — except every hop is a real, verifiable tool call, not the model filling in the gaps from memory:

- **Target & mechanism research**: go from a gene or protein to its structure, pathways, interaction partners, and known drugs in one pass (Ensembl/UniProt → PDB/AlphaFold → KEGG/Reactome/STRING → Open Targets/ChEMBL).
- **Drug discovery triage**: find active compounds, understand mechanism of action, and run a real molecular docking pose against a target structure, cross-referenced against trial status and label data for anything already approved.
- **Variant interpretation**: pull clinical significance and population allele frequency for the same variant side by side (ClinVar + gnomAD), the two numbers you need together to judge pathogenicity.
- **Literature-grounded due diligence**: search PubMed and get a compliance-checked answer on legal full-text availability (open access vs. Sci-Hub, tier always disclosed), every claim citable back to a PMID or DOI.
- **Systems-level modeling**: real flux balance analysis on a genome-scale metabolic model (an actual constraint-based optimization, not a pathway diagram).
- **Microbiome composition analysis**: real diversity statistics computed locally on your own abundance data, no upload to a third-party service.
- **Regulatory/commercial due diligence**: trial status and drug label lookups in one place, aimed at the commercial/pharma research persona specifically, not just academic literature search.

## Open by design, not just by license

The MIT license is the easy part. What actually makes this open science infrastructure, not just open-source code:

- **Runs on your own machine, under your own control.** Nothing about a research question you ask it has to leave your infrastructure — self-hosted Mattermost, your own Postgres, your own Docker stack. No API waits on a vendor's roadmap or a subscription tier to get access to a real capability.
- **The tool roster is a pattern anyone can extend**, not a fixed menu: a new scientific tool is a builder file plus a registration line (`CONTRIBUTING.md`'s documented recipe), the same shape every one of the 37 tools wired in today already follows. Every one of them is real, live-verified code, not a wrapper around a promise.
- **Works with a Claude subscription, not just a metered API key** — the whole point of connecting an LLM to real tools shouldn't come with a second paywall on top of the first.
- **Every claim is checkable against the exact tool call that produced it** — an open agent that can't show its work isn't meaningfully more trustworthy than a closed one. Grounding isn't a feature flag here; it's enforced in code (`app/grounding.py`) on every single response.

## Getting started

**Prerequisites:** Docker + Docker Compose v2. That's it — this works the same way on **Mac, Linux, and Windows** (Docker Desktop on Mac/Windows, Docker Engine on Linux); every service, including the `claude` CLI itself, runs inside containers, so nothing OS-specific is required on the host. (The bootstrap script in step 4 needs *some* Python 3.9+ on the host too, but nothing else does.)

**1. Clone and configure**

```bash
git clone https://github.com/RohanV01/AI-BioScientist.git
cd AI-BioScientist
cp .env.example .env
```

Generate two real secrets and paste them into `.env` (`.env.example` ships a placeholder
password and a blank vault key on purpose -- a checked-in shared default is fine for a
five-minute local trial, but not for anything another person can reach):

```bash
# POSTGRES_PASSWORD -- replaces the public dev_only_change_me default
openssl rand -base64 24

# CREDENTIAL_VAULT_KEY -- required before adding any BYO credential (see "BYO credentials" below)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep `CREDENTIAL_VAULT_KEY` somewhere durable outside `.env` too -- losing it makes every
already-stored credential permanently undecryptable, and there's no rotate-in-place migration yet
(re-adding each credential from scratch is the only recovery path).

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
  It prints a URL + code — open it in a browser on any device (doesn't have to be this machine) and approve. Credentials land in the `orchestrator_home` Docker volume and persist across restarts; you won't be asked again unless you `docker compose down -v`.

**4. Bootstrap Mattermost** — creates the admin account, team, bot, and the webhook that wires the agent in (pure Python, same command on every OS, no bash/curl/jq needed):

```bash
python scripts/bootstrap_mattermost.py
```
Prints the generated admin password once (also saved to `.env`). Under "Next steps," it prints a ready-to-run `seed_dev_data.py` command with the real `--team-id`/`--bot-user-id`/`--bot-token`/`--grounding-log-channel-id` values filled in — copy that exact line for the next step. **Don't skip `--bot-token`**: without it the seeded agent has no way to post replies in Mattermost at all, and the failure is silent from the chat side (only visible in `docker compose logs orchestrator` as "Agent ... has no bot token configured").

**5. Seed the agent's tool roster** — run inside the container (there's no host Python venv on a fresh clone), using the exact command step 4 printed:

```bash
docker compose exec orchestrator python scripts/seed_dev_data.py --team-id <...> --bot-user-id <...> --bot-token <...> --grounding-log-channel-id <...>
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

**Full-text paper downloads work out of the box.** `download_paper` (`orchestrator/app/tools/literature_discovery.py`) tries a direct open-access download first (no browser involved) and falls back to the [Camofox stealth browser](https://github.com/jo-inc/camofox-browser) for genuinely paywalled DOIs, driving the real Sci-Hub UI (paste the DOI, click open, click the page's own save button) and capturing the resulting browser download. `docker compose up -d` already starts Camofox as its own service (`ghcr.io/jo-inc/camofox-browser`, no separate clone/install step needed) -- `.env.example`'s defaults point the orchestrator at it correctly. The only thing worth customizing is `SCIHUB_MIRROR_URLS` in `.env` (comma-separated Sci-Hub mirrors; list every one you know is currently working, since mirrors go down/get blocked independently) -- `.env.example` ships a reasonable starting list already.

Every download is checked against the paper's own expected title/DOI (`_verify_pdf_content` in `literature_discovery.py`) before anything downstream trusts it -- a real browser download can succeed end-to-end while a Sci-Hub mirror quietly serves the wrong paper's PDF for a given DOI (seen live during testing). A flagged mismatch is reported in `download_paper`'s own result text, and `read_paper` refuses to extract "findings" from a file flagged that way.

**Research experiments.** Every research investigation gets its own folder (`data/Experiments/<id>/`) and DB row -- control it with the `/experiment` Slash Command (`start ["name"]` / `end` / `status` / `conclude`), or just message `@orchestrator` and one opens automatically. Register the command once per Mattermost instance:
```bash
# 1. Get a session token by logging in as the admin account step 4 created
#    (same login-endpoint trick bootstrap_mattermost.py itself uses --
#    the token comes back in the response's Token header, not the body).
ADMIN_TOKEN=$(curl -si -X POST http://localhost:8065/api/v4/users/login \
  -d '{"login_id": "admin", "password": "<the admin password step 4 printed>"}' \
  | grep -i '^Token:' | tr -d '\r' | cut -d' ' -f2)

# 2. Get your team id (also printed by step 4, if you still have that output).
TEAM_ID=$(curl -s http://localhost:8065/api/v4/teams/name/openbiolab \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

# 3. Register the command. url is the orchestrator's container-network
#    address (Mattermost calls it via Docker's internal DNS, the same
#    "orchestrator" hostname bootstrap_mattermost.py's own webhook uses) --
#    not localhost, even though you reach Mattermost itself at localhost.
curl -X POST http://localhost:8065/api/v4/commands \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"team_id\": \"$TEAM_ID\", \"trigger\": \"experiment\", \"method\": \"P\",
       \"url\": \"http://orchestrator:8000/webhooks/mattermost/experiment\",
       \"auto_complete\": true, \"display_name\": \"Experiment\",
       \"description\": \"Controls the current research experiment for this channel\"}"
```
Copy the response's own `token` field into `.env` as `MATTERMOST_EXPERIMENT_COMMAND_SECRET` (a separate value from `MATTERMOST_WEBHOOK_SECRET` -- Mattermost auto-generates one token per integration, no way to set a custom one), then `docker compose up -d --force-recreate orchestrator` to pick it up.

`read_paper`'s structured extraction and `/experiment conclude`'s synthesis run through a modular one-shot LLM backend (`orchestrator/app/llm_backend.py`), not tied to any single provider: it tries a real Anthropic API key (`ANTHROPIC_API_KEY`), then a local [LM Studio](https://lmstudio.ai) server (`LM_STUDIO_BASE_URL`), then falls back to the `claude` CLI's own subscription login from step 5 above -- so both features work with zero extra setup if you already logged in there. Set `LLM_BACKEND` in `.env` to pin one explicitly instead of the default `auto` fallback chain.

## Contributing

New tool sources, new workflow combos, bug reports — all welcome. `CONTRIBUTING.md` documents the exact recipe for wiring in a new scientific tool; if this project's mission (open, self-hostable, verifiable AI-driven science) resonates, the fastest way to help is adding one.

## Change history

See [`CHANGELOG.md`](CHANGELOG.md).
