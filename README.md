# AI Scientist

A local-first research platform: a Mattermost-based messaging workspace where you delegate research tasks to specialized domain agents — genomics, drug discovery, literature, structural biology, systems biology, clinical/commercial ops, microbiome/immunology — instead of manually stitching together a dozen databases and tools by hand. Every agent runs on Claude Code/Codex, calls real MCP-wired tools, and every response carries a traceable link back to the tool call, record, or citation that produced it.

## Status

**Planning complete, build starting.** See `docs/` for the full spec. Nothing here runs yet — Phase 0 of `docs/10-build-plan.md` is the current work.

## Why this exists

This is the build-out of the [Researcher's Lab report](../Daily%20Learning/Vault/Ideas/researcher-lab-experiment-catalog-2026-08-15.md) — 105 candidate experiments across 7 domains, a gap analysis, and a confirmed product vision (local-first, Claude Code-native, Slack-style delegation, grounded output). That report is this project's requirements source.

## What's already here

- **`data/`** — bulk local data assets (not in git, see `.gitignore`): `scihub.sql` (32.7GB Sci-Hub metadata dump — DOI, Title, Author, Year, Journal, PubmedID, PMC) and `Databases/` (52GB of already-local bulk copies of ChEMBL, STRING, GTEx, GWAS Catalog, OMIM, BioGRID, DepMap, PrimeKG, AlphaMissense, and more).
- **`reference/rxdis-legacy/`** — RxDis, a working 9-phase local-first drug-discovery pipeline (target ID → validation → repurposing/de novo design → biologics → optimization → packaging) built before this project's messaging-layer pivot. Its code was removed (superseded by the plan in `docs/`), but its docs, design notes, and phase summaries are kept as reference — and its FastAPI service is the first non-trivial agent this project wraps (`docs/10-build-plan.md` Phase 2).
- **`docs/`** — the full planning suite: goals, PRD, personas, architecture, data model, UX behavior, cross-feature journeys, test strategy, and the build plan.

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

## Stack (see `docs/07-system-architecture.md` for the full rationale)

- **Messaging:** Mattermost (self-hosted, Go + React + Postgres, MIT core)
- **Orchestration:** Python/FastAPI (Orchestrator Service) + Claude Code/Codex (agentic runtime, via MCP)
- **First two agents:** Literature (PubMed MCP, live) and Drug Discovery (wraps RxDis)
- **Data:** Postgres (Orchestrator + Mattermost schemas) + local bulk data (`data/`) queried in place

## Change history

See `CHANGELOG.md`.
