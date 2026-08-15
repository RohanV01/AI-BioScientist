# Build Plan

Phased, each phase ending in something demonstrably working — not a phase boundary drawn for its own sake. Cross-referenced to the research report's Section 6 (Prioritized Shortlist) and Section 9 (Feasibility Check) so prioritization isn't invented fresh here. **See `11-backlog-traceability.md` for the full status of every one of the report's 105 experiments, 8 flagships, 10 gaps, and 13 paid integrations against these phases** — this document only names what's actually scheduled; it isn't a complete map of the report on its own.

## Phase 0 — Data audit & foundations (before any agent code)

**Goal:** de-risk the two biggest unknowns before building on top of them.

- [ ] Run the `scihub.sql` + `biology_dois.txt` join (see `01-project-goals.md`); measure coverage (AC-11). This is the single highest-leverage task in the whole plan — if coverage is high, Gap 1 from the research report is effectively solved without the CrossRef/Unpaywall pipeline it originally proposed.
- [ ] Decide `scihub.sql` serving mechanism: local MySQL/MariaDB (matches the dump's native format) vs. converting to DuckDB/Parquet (matches the pattern already used by the DOI-biology-classifier project). Bias toward whichever is faster to stand up given the 32.7GB size — this is an infra decision, not a research one.
- [ ] Stand up Mattermost locally (docker-compose), confirm Bot Accounts + Outgoing Webhooks work with a trivial echo bot — proves the messaging-layer mechanics before any agent logic exists.
- [ ] Scaffold the Orchestrator Service (FastAPI skeleton, `06-data-model.md` schema migrated, empty Agent Registry).
- [ ] Confirm RxDis still runs standalone post-move (it now lives at `reference/rxdis-legacy/`, referencing `data/Databases/` and `data/scihub.sql` at their new paths — path references inside RxDis's own config almost certainly need updating).
- [ ] **Promoted from the backlog audit:** scope the Gap 9 compliance boundary (full-text sourcing must not inherit sci-hub provenance) explicitly, now that `data/scihub.sql` gives this platform direct access to sci-hub-sourced metadata (and, via MD5/Filesize fields in the dump, an implicit path to sci-hub-sourced full text). Decide and document, before Phase 1 ships anything literature-facing: the Literature Agent may use `scihub.sql` for metadata/citation lookups, but full-text retrieval must route through PubMed OA/PMC/Unpaywall-resolved links only, never through any MD5/file-hash-based access the dump makes technically possible. This was implicit in the research report; it's a concrete build task now that the data is actually on disk.

**Exit criterion:** a message sent to a trivial Mattermost bot triggers a stub Orchestrator response, the DOI-join coverage number is known, and the Gap 9 compliance boundary is written down somewhere Phase 1 will actually reference.

## Phase 1 — First real agent: Literature (Tier 1 · research report Shortlist #9 pattern — ships on zero new wiring)

- [ ] Wire PubMed MCP into the Orchestrator's Claude Code/Codex Runner for one agent.
- [ ] Build the Grounding Layer's core enforcement (`provenance_type`, `GROUNDING_LINK` writes) — this is shared infrastructure every future agent depends on, so it's built once, here, not per-agent.
- [ ] Journey 1 end-to-end (`08-cross-feature-journeys.md`), AC-1/AC-2/AC-4 passing.

**Exit criterion:** Priya's persona scenario works for real, against a live Mattermost instance, with real PubMed calls.

## Phase 2 — Second agent: Drug Discovery, wrapping RxDis (Tier 1 for the science legs · Tier 2/procurement for the DrugBank credential)

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

## Phase 4 — Third+ agents (Tier 2, wiring-only for all four) — following the research report's shortlist order

Wire additional domain agents in the order the research report's Section 6 (Prioritized Build Shortlist) and Section 9 (Feasibility Check) already justify — not re-litigated here:

- [ ] **Genomics Agent** — wire Ensembl/UniProt/ClinVar/gnomAD (Shortlist #2), unlocking Genomics #1/#2/#3/#6/#7/#12/#15/#16. **Also wire the Ontologies domain here** (Gene Ontology, HPO, NCBI Taxonomy, ICD at minimum) — flagged in `11-backlog-traceability.md` §5 as genuinely missing from the report's own build-out, and this is the natural point to add it since ontology normalization underpins cross-database entity matching for Flagship 5.3/5.4.
- [ ] **Systems Biology Agent** — wire KEGG/Reactome/STRING (Shortlist #5; STRING is also already present locally in `data/Databases/` — confirm whether local data or live API is the better source before wiring).
- [ ] **Clinical/Commercial Agent** — wire ClinicalTrials.gov/DailyMed/PharmGKB (Shortlist #6), with Phase 3's review-marker convention applied from day one, not retrofitted.
- [ ] **Structural Biology Agent** — wire PDB/AlphaFold DB (Shortlist #8); note this is also where Gap 7 (compute) first becomes unavoidable for anything beyond simple structure lookup — defer docking/folding-inference capability to Phase 5.

**Exit criterion:** Journey 6 (multi-agent flagship pipeline) becomes testable once ≥2 agents beyond Drug Discovery/Literature exist — run it for real, not just as a written scenario.

## Phase 5 — Compute layer (Gap 7) and the sandboxed tool-runner (Section 7)

Section 7's actual strategy, summarized (full detail in the report, not reproduced here): API-callable tool sources wrap cheaply and need no compute of their own; local CLI/binary tool sources (the majority of the 33,110-entry bio.tools catalog) need a sandboxed execution environment, which is the harder half of this phase. The report's own phasing: (1) wrap the highest-experiment-density, permissively-licensed, API-callable subset first — Immunoinformatics and Cheminformatics; (2) build the sandbox before touching Structural-Biology/Molecular-Dynamics, which get zero benefit from an API-only wrapper; (3) wrap the rest demand-driven, not upfront. This phase follows that order.

- [ ] **Check Hugging Face first** (per `07-system-architecture.md`'s compute-layer note) for any given compute-blocked experiment before deciding buy-vs-build below — this can shrink how much of Gap 7 actually needs NVIDIA/cloud GPU or the sandbox at all.
- [ ] Decide buy-vs-build per the research report's Section 9 feasibility rating (Tier 2, procurement blocker) for NVIDIA Platform/cloud GPU — hosted-inference-shaped needs (folding, docking) — vs. the containerized tool-runner (Tier 3, compute-infra blocker, higher effort) for the CLI/binary bio.tools long tail.
- [ ] First wrap of a Phase-1-priority bio.tools category (Immunoinformatics or Cheminformatics, per Section 7's prioritization table — both API-callable-heavy, no sandbox required yet).
- [ ] License-compatibility gate (Section 7) — automated check before any GPL/AGPL-licensed wrapped tool is exposed to a commercial-tier context.

**Exit criterion:** at least one previously-uncallable bio.tools entry is a working agent capability, proving the wrapping pattern from Section 7 generalizes beyond the already-live MCPs.

## Ongoing, not phase-bound

- Update `researcher-lab-experiment-catalog-2026-08-15.md`'s gap analysis once the Phase 0 data audit confirms how much of Gap 1 the local join actually solves, and once `data/Databases/`'s existing local ChEMBL/STRING/GTEx/GWAS Catalog/OMIM/BioGRID/DepMap/PrimeKG/AlphaMissense holdings are confirmed to upgrade specific Tier-2 gap ratings to Tier-1 — this was discovered *during* this project's kickoff and the report doesn't reflect it yet.
- `CHANGELOG.md` (repo root) — every phase completion and every architecture decision reversal gets an entry.
- The auto-memory project file — kept current with what's actually built vs. planned, so future sessions don't re-derive this plan from scratch.

## Related documents

All of `docs/` — this is the plan that ties them together. `11-backlog-traceability.md` for the full report-to-phase mapping. Primary upstream source: [[researcher-lab-experiment-catalog-2026-08-15]].
