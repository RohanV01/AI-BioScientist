# Build Plan

Phased, each phase ending in something demonstrably working — not a phase boundary drawn for its own sake. Cross-referenced to the research report's Section 6 (Prioritized Shortlist) and Section 9 (Feasibility Check) so prioritization isn't invented fresh here.

## Phase 0 — Data audit & foundations (before any agent code)

**Goal:** de-risk the two biggest unknowns before building on top of them.

- [ ] Run the `scihub.sql` + `biology_dois.txt` join (see `01-project-goals.md`); measure coverage (AC-11). This is the single highest-leverage task in the whole plan — if coverage is high, Gap 1 from the research report is effectively solved without the CrossRef/Unpaywall pipeline it originally proposed.
- [ ] Decide `scihub.sql` serving mechanism: local MySQL/MariaDB (matches the dump's native format) vs. converting to DuckDB/Parquet (matches the pattern already used by the DOI-biology-classifier project). Bias toward whichever is faster to stand up given the 32.7GB size — this is an infra decision, not a research one.
- [ ] Stand up Mattermost locally (docker-compose), confirm Bot Accounts + Outgoing Webhooks work with a trivial echo bot — proves the messaging-layer mechanics before any agent logic exists.
- [ ] Scaffold the Orchestrator Service (FastAPI skeleton, `06-data-model.md` schema migrated, empty Agent Registry).
- [ ] Confirm RxDis still runs standalone post-move (it now lives at `reference/rxdis-legacy/`, referencing `data/Databases/` and `data/scihub.sql` at their new paths — path references inside RxDis's own config almost certainly need updating).

**Exit criterion:** a message sent to a trivial Mattermost bot triggers a stub Orchestrator response, and the DOI-join coverage number is known.

## Phase 1 — First real agent: Literature (research report Shortlist #9 pattern — ships on zero new wiring)

- [ ] Wire PubMed MCP into the Orchestrator's Claude Code/Codex Runner for one agent.
- [ ] Build the Grounding Layer's core enforcement (`provenance_type`, `GROUNDING_LINK` writes) — this is shared infrastructure every future agent depends on, so it's built once, here, not per-agent.
- [ ] Journey 1 end-to-end (`08-cross-feature-journeys.md`), AC-1/AC-2/AC-4 passing.

**Exit criterion:** Priya's persona scenario works for real, against a live Mattermost instance, with real PubMed calls.

## Phase 2 — Second agent: Drug Discovery, wrapping RxDis

- [ ] Build the RxDis MCP wrapper (trigger pipeline run, poll status, map RxDis's own provenance data into `GROUNDING_LINK` rows).
- [ ] Progress-update posting (FR-7) — RxDis's phase-transition events need a hook the wrapper can subscribe to; check whether RxDis's existing FastAPI already emits phase events (`api/orchestrator.py` per the legacy README's architecture section) before building a new one.
- [ ] Wire ChEMBL + Open Targets MCPs into this agent too (already-live, zero new wiring — research report Shortlist #3/#4).
- [ ] Journey 2 end-to-end, AC-3/AC-5/AC-6 passing.
- [ ] First cut of the Credential Vault (`CREDENTIAL` table, basic encryption) — needed because RxDis's own dependency list likely includes at least one paid/rate-limited source worth BYO-credentialing (confirm against `reference/rxdis-legacy/requirements.txt` and `DESIGN.md`).
- [ ] Journey 3/4 end-to-end, AC-7/AC-8 passing.

**Exit criterion:** Marcus's persona scenario works end-to-end, including the credential-missing graceful-degradation path.

## Phase 3 — Grounding hardening + first regulatory-adjacent flag

- [ ] Message-attachment structured-output rendering (UX Behavior §3) — needed once responses get complex enough that plain text stops being legible (Flagship-style dossiers).
- [ ] The reserved "requires expert review" visual marker (UX Behavior §4) — build and test even before the Clinical/Commercial Agent exists for real, using Journey 5 as the test scenario, so the marker convention is locked in before more agents start using (or misusing) it.
- [ ] `#grounding-log` audit channel (FR-10) — the human-facing surface of the `TOOL_CALL` table.

**Exit criterion:** AC-9 passing; the visual-marker convention is documented and enforced in code, not just in this doc.

## Phase 4 — Third+ agents, following the research report's shortlist order

Wire additional domain agents in the order the research report's Section 6 (Prioritized Build Shortlist) and Section 9 (Feasibility Check) already justify — not re-litigated here:

- [ ] **Genomics Agent** — wire Ensembl/UniProt/ClinVar/gnomAD (Shortlist #2), unlocking Genomics #1/#2/#3/#6/#7/#12/#15/#16.
- [ ] **Systems Biology Agent** — wire KEGG/Reactome/STRING (Shortlist #5; STRING is also already present locally in `data/Databases/` — confirm whether local data or live API is the better source before wiring).
- [ ] **Clinical/Commercial Agent** — wire ClinicalTrials.gov/DailyMed/PharmGKB (Shortlist #6), with Phase 3's review-marker convention applied from day one, not retrofitted.
- [ ] **Structural Biology Agent** — wire PDB/AlphaFold DB (Shortlist #8); note this is also where Gap 7 (compute) first becomes unavoidable for anything beyond simple structure lookup — defer docking/folding-inference capability to Phase 5.

**Exit criterion:** Journey 6 (multi-agent flagship pipeline) becomes testable once ≥2 agents beyond Drug Discovery/Literature exist — run it for real, not just as a written scenario.

## Phase 5 — Compute layer (Gap 7) and the sandboxed tool-runner (Section 7)

- [ ] Decide buy-vs-build per the research report's Section 9 feasibility rating: NVIDIA Platform/cloud GPU (buy, fast) for hosted-inference-shaped needs (folding, docking) vs. the containerized tool-runner (build, higher effort) for the CLI/binary bio.tools long tail.
- [ ] First wrap of a Phase-1-priority bio.tools category (Immunoinformatics or Cheminformatics, per Section 7's prioritization table) through whichever path was chosen.
- [ ] License-compatibility gate (Section 7) — automated check before any GPL/AGPL-licensed wrapped tool is exposed to a commercial-tier context.

**Exit criterion:** at least one previously-uncallable bio.tools entry is a working agent capability, proving the wrapping pattern from Section 7 generalizes beyond the already-live MCPs.

## Ongoing, not phase-bound

- Update `researcher-lab-experiment-catalog-2026-08-15.md`'s gap analysis once the Phase 0 data audit confirms how much of Gap 1 the local join actually solves, and once `data/Databases/`'s existing local ChEMBL/STRING/GTEx/GWAS Catalog/OMIM/BioGRID/DepMap/PrimeKG/AlphaMissense holdings are confirmed to upgrade specific Tier-2 gap ratings to Tier-1 — this was discovered *during* this project's kickoff and the report doesn't reflect it yet.
- `CHANGELOG.md` (repo root) — every phase completion and every architecture decision reversal gets an entry.
- The auto-memory project file — kept current with what's actually built vs. planned, so future sessions don't re-derive this plan from scratch.

## Related documents

All of `docs/` — this is the plan that ties them together. Primary upstream source: [[researcher-lab-experiment-catalog-2026-08-15]].
