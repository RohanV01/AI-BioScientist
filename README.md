# AI Scientist

A local-first research platform: a Mattermost-based messaging workspace where you delegate research tasks to specialized domain agents — genomics, drug discovery, literature, structural biology, systems biology, clinical/commercial ops, microbiome/immunology — instead of manually stitching together a dozen databases and tools by hand. Every agent runs on Claude Code/Codex, calls real MCP-wired tools, and every response carries a traceable link back to the tool call, record, or citation that produced it.

## Status

**Build in progress — Phase 0 of `docs/10-build-plan.md`.** Planning is complete (`docs/`); the messaging layer and orchestrator skeleton are being stood up now. Nothing is feature-complete yet — see `CHANGELOG.md` for exactly what runs today.

## Why this exists

This is the build-out of a research report — 105 candidate research-agent experiments across 7 domains, a gap analysis, and a confirmed product vision (local-first, Claude Code-native, Slack-style delegation, grounded output) — written by the author before this repo existed. That report lives outside this repo (a personal research vault, not redistributed here) and is referenced throughout `docs/` as `[[researcher-lab-experiment-catalog-2026-08-15]]`; treat those references as "the design rationale lives elsewhere," not as working links.

## Getting started

**Prerequisites:** Docker + Docker Compose v2, Python 3.11+.

```bash
git clone <this-repo-url>
cd ai-scientist
cp .env.example .env        # edit if you want a non-default Postgres password
docker compose up -d postgres
# wait for postgres to report healthy, then:
docker compose up -d mattermost
```

Mattermost will be reachable at `http://localhost:8065` — first visit creates the initial admin account. The Orchestrator Service (`orchestrator/`) is added to `docker-compose.yml` once its skeleton exists (Build Plan Phase 0, in progress); until then, Mattermost runs standalone with no agents wired up.

**Optional bulk data:** none of the above requires it. If you have (or want to build) the local bibliographic/database corpus some agents can use, see `data/README.md` — it's entirely optional and gitignored, and every agent is designed to degrade gracefully without it (`docs/05-ux-behavior.md` §1).

**Everything else you might want to reuse:** `reference/rxdis-legacy/` contains a previously-built 9-phase local-first drug-discovery pipeline (RxDis) whose application code was removed in favor of the plan in `docs/`, but whose design docs are kept — see `docs/10-build-plan.md` Phase 2 for how it gets wrapped back in as an agent, not rebuilt.

## What's already here

- **`docker-compose.yml`, `.env.example`, `mattermost-server/`** — the local dev stack (Postgres + Mattermost); see Getting Started above.
- **`docs/`** — the full planning suite: goals, PRD, personas, architecture, data model, UX behavior, cross-feature journeys, test strategy, build plan, and a backlog/traceability index.
- **`reference/rxdis-legacy/`** — design docs and notes from RxDis, the prior drug-discovery pipeline this project wraps rather than rebuilds (see above).
- **`data/`** (gitignored, not part of a fresh clone) — see `data/README.md`.

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
11. `docs/11-backlog-traceability.md` — full status of every experiment/flagship/gap/paid-tool from the research report against these phases (read this before assuming anything from the report is "handled" just because it's referenced elsewhere)

## Stack (see `docs/07-system-architecture.md` for the full rationale)

- **Messaging:** Mattermost (self-hosted, Go + React + Postgres, MIT core)
- **Orchestration:** Python/FastAPI (Orchestrator Service) + Claude Code/Codex (agentic runtime, via MCP)
- **First two agents:** Literature (PubMed MCP, live) and Drug Discovery (wraps RxDis)
- **Data:** Postgres (Orchestrator + Mattermost schemas) + local bulk data (`data/`) queried in place

## Change history

See `CHANGELOG.md`.
