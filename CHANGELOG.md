# Changelog

All notable changes to this project are logged here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/); dates in `YYYY-MM-DD`.

## [Unreleased]

### Changed — 2026-08-24
- **Extracted `rxdis/` into its own standalone project** at `/home/rohanvyas/Documents/rxdis` (own git repo, history preserved via `git subtree split -P rxdis`). It's a self-contained pipeline with no dependency from `orchestrator/` on it, so this doesn't affect the platform. `docs/10-build-plan.md`'s open task about wrapping RxDis phases as individually-callable tools is unaffected by the extraction — it will just pull from the new path.

### Changed — 2026-08-17
- **Containerized the Claude Code/Codex Runner and made setup cross-platform** (Mac/Linux/Windows), closing the "Ongoing" item tracked in `docs/10-build-plan.md`. `orchestrator/Dockerfile` now installs Node.js 20 + the `claude` CLI and runs as a non-root user; the orchestrator no longer depends on a `claude` CLI already installed and authenticated on the developer's own host, which was a real bug found live: the host-run orchestrator had silently drifted to binding `127.0.0.1` instead of `0.0.0.0`, making it unreachable from Mattermost's `host.docker.internal` webhook callback with no error surfaced anywhere. Both Claude auth methods are supported without forcing a switch: `ANTHROPIC_API_KEY` (headless) or a one-time `docker compose exec orchestrator claude login` for a Pro/Max subscription with no API key, persisted in a new `claude_config` Docker volume — `docker-compose.yml` documents both. Replaced `scripts/bootstrap_mattermost.sh` (bash+curl+jq) with `scripts/bootstrap_mattermost.py` (stdlib-only Python), since the SDK itself refuses to run npm's Windows `claude.cmd` shim — native Windows host execution was never viable, so everything now runs in Linux containers via Docker Desktop instead, with `README.md`'s Getting Started section rewritten to match.
- Product renamed from "AI Scientist" to **OpenBioLab** across the README, `CONTRIBUTING.md`, `docs/01-project-goals.md`, `docs/04-information-architecture.md`, `.env.example`, and the orchestrator (`app/main.py`'s FastAPI title, `app/claude_runner.py`'s system prompt and agent-workdir prefix, `pyproject.toml`'s package name, `scripts/seed_dev_data.py`'s default agent name), plus the Docker container names in `docker-compose.yml` and the default Mattermost team name/display name in `.env.example`. The GitHub repo slug (`RohanV01/AI-BioScientist`) was intentionally left unchanged — that's a separate, more disruptive decision (breaks old clone URLs/links) not yet made.
- Closed a real default-credential gap ahead of the repo going public: `.env.example` previously shipped a real-looking default `MM_ADMIN_PASSWORD`, which `scripts/bootstrap_mattermost.sh` used to actually create the Mattermost admin account via the API — anyone who didn't override it got the same known password. Fixed by generating a random password on first bootstrap run (same pattern the script already used for `MATTERMOST_WEBHOOK_SECRET`): written into `.env`, printed once, never a shared default.

### Added — 2026-08-15 (traceability pass)
- `docs/11-backlog-traceability.md` — full status index mapping all 105 experiments, 8 flagships, 10 gaps, 13 paid integrations, and Section 10's overlooked-resource findings from the Researcher's Lab report against actual Build Plan phases. Added after an audit found the original `docs/` suite covered its own MVP scope in real detail but only referenced (not tracked) most of the report's breadth — see "Changed" below for what got fixed as a result.

### Changed — 2026-08-15 (traceability pass)
- `docs/07-system-architecture.md` — added a Compute Layer subsection: check Hugging Face (already connected, previously unused anywhere in these docs) before defaulting to NVIDIA Platform/cloud GPU for Gap 7; added the AlphaFold Server non-commercial-ToS trap as an explicit tool-selection check for the Structural Biology Agent, gated on org tier.
- `docs/10-build-plan.md` — Phase 0 gained an explicit Gap 9 (sci-hub full-text compliance) scoping task, promoted from implicit to concrete now that `data/scihub.sql`'s MD5/Filesize fields make full-text access technically possible, not just metadata; Phase 4's Genomics Agent step now also covers wiring the Ontologies domain (previously absent entirely); Phase 5 expanded with Section 7's actual 3-phase wrapping rationale instead of a bare cross-reference; phase headers tagged with Tier ratings from the report's Section 9.

### Added — 2026-08-15
- Full planning document suite in `docs/`: project goals, PRD, user personas, information architecture, UX behavior, data model, system architecture, cross-feature journeys, test strategy + acceptance criteria, and a phased build plan.
- `README.md` rewritten for the new project direction (Mattermost-based multi-agent messaging platform, superseding the prior single-purpose RxDis README at that path).
- This changelog and the project's auto-memory entry.

### Changed — 2026-08-15
- Repository re-scoped from a single drug-discovery pipeline (RxDis) to a broader multi-agent research platform, per the confirmed product vision in [[researcher-lab-experiment-catalog-2026-08-15]] Section 11.
- Reorganized the folder: legacy RxDis docs/notes moved to `reference/rxdis-legacy/`; bulk data (`scihub.sql`, `Databases/`) moved to `data/`.
- `.gitignore` rewritten for the new project structure (data/, node_modules, Go build artifacts, Mattermost runtime config).

### Removed — 2026-08-15
- RxDis's application code (`src/`, `frontend/`, `scripts/`, `tools/`, `testing/`, `docker-compose.yml`, `Dockerfile`) and its build artifacts (`.venv/`, `.serena/`). Design docs, memory notes, and data were explicitly kept — see `reference/rxdis-legacy/` and `data/`. RxDis's FastAPI service is planned to be re-wrapped as an MCP tool source in Build Plan Phase 2, not reimplemented.

### Discovered — 2026-08-15
- `data/scihub.sql` (32.7GB) turns out to be a full Sci-Hub `scimag` metadata dump (DOI, Title, Author, Year, Journal, PubmedID, PMC per record) — potentially resolves Gap 1 from the Researcher's Lab report (the DOI-biology-classifier corpus having no metadata) via a local join, without rebuilding the CrossRef/Unpaywall enrichment pipeline that report originally proposed. Confirming this is Build Plan Phase 0's first task.
- `data/Databases/` (52GB) already contains local bulk copies of ChEMBL, STRING, GTEx, GWAS Catalog, OMIM, BioGRID, DepMap, PrimeKG, and AlphaMissense — several of these upgrade specific Tier-2 ("needs MCP wiring") gaps from the research report toward Tier-1 ("already have local data"). The research report itself has not yet been updated to reflect this — flagged as an open follow-up in `docs/10-build-plan.md`.

---

## How to use this file

- Every Build Plan phase completion gets an entry.
- Every architecture decision reversal (e.g. if Mattermost gets replaced, if the credential-vault key-management approach changes) gets an entry, even before code exists — decisions are logged when made, not just when shipped.
