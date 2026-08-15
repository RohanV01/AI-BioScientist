# `data/` — optional bulk local data

Nothing in this folder is required to clone, install, or run the core platform (Mattermost + Orchestrator + the Literature Agent all work without it). It's gitignored — a fresh clone will not have it, and that's expected.

## What can live here

| Path | What it is | Required for |
|---|---|---|
| `scihub.sql` | A MySQL dump of bibliographic metadata (DOI, title, author, year, journal, etc.) keyed by DOI, used for literature-enrichment lookups. | The DOI-corpus-enrichment flow described in `docs/01-project-goals.md` and `docs/10-build-plan.md` Phase 0. Without it, the Literature Agent still works fully via the live PubMed MCP — this only extends coverage. |
| `Databases/` | Local bulk copies of public bio/chem databases (ChEMBL, STRING, GTEx, GWAS Catalog, OMIM, BioGRID, DepMap, PrimeKG, AlphaMissense, etc.) for offline/high-throughput querying instead of hitting live APIs. | Nothing at MVP — every agent in Phases 1–2 uses live MCPs. Relevant once Phase 4/5 agents want a local-data option over an API call (see `docs/07-system-architecture.md`). |
| `scihub_meta.duckdb` | Generated locally by `scripts/parse_scihub_to_duckdb.py` from `scihub.sql` — not something you fetch, something you build (see below). | Same as `scihub.sql` above. |

## If you don't have this data

Everything in `docs/` that references `data/` degrades gracefully without it — treat any reference to these paths in the docs as "if present," not "required." No agent should hard-fail because this folder is empty; if you find one that does, that's a bug (file it against `docs/09-test-strategy-acceptance-criteria.md`'s coverage, since graceful degradation for missing/unwired sources is already a stated requirement — see UX Behavior §1's failure-behavior rule).

## If you want to populate this data yourself

- `scihub.sql`-equivalent data: any bibliographic metadata source keyed by DOI (title/author/year/journal) can substitute — the parser in `scripts/parse_scihub_to_duckdb.py` expects the specific `scimag` table schema of this particular dump; adapt the column-name mapping at the top of that script for a different source.
- `Databases/`-equivalent data: each subdirectory corresponds to a public database with its own official bulk-download instructions (ChEMBL, GTEx, GWAS Catalog, etc. all publish downloadable dumps) — see `docs/01-source-inventory` references inside the research report ([[researcher-lab-experiment-catalog-2026-08-15]] Section 1) for where each one comes from.

Nothing here is licensed for redistribution as part of this repo, which is exactly why it's gitignored rather than checked in.
