# Build Plan

Phased, each phase ending in something demonstrably working — not a phase boundary drawn for its own sake. Cross-referenced to the research report's Section 6 (Prioritized Shortlist) and Section 9 (Feasibility Check) so prioritization isn't invented fresh here. **See `11-backlog-traceability.md` for the full status of every one of the report's 105 experiments, 8 flagships, 10 gaps, and 13 paid integrations against these phases** — this document only names what's actually scheduled; it isn't a complete map of the report on its own.

## Architecture pivot (2026-08-15) — read before continuing past Phase 1

Phases 0 and 1 below were built and verified under the *original* design: one bot per research-report domain cluster (a "Literature Agent," a future "Drug Discovery Agent," etc.), each with its own narrow tool scope. **That's not the product** — see `07-system-architecture.md`'s pivot note for the full reasoning. The actual model: **one master orchestrator agent**, with the entire tool roster attached, that plans a methodology per query, executes across whatever tools that plan needs, and synthesizes a grounded report.

**What this means for what was already built:** nothing from Phase 0/1 was wasted, but Phase 2 now starts with a refactor, not new-agent work. `app/claude_runner.py`'s `run_literature_agent()` is domain-specific (hardcoded to the PubMed tool, a Literature-Agent-flavored system prompt) — it needs to become the general Plan→Execute→Synthesize runner, parameterized by *whatever tools are wired*, not one function per domain. The PubMed tool, the Grounding Layer, the isolation fix (`setting_sources=[]`), the ToolCall/GroundingLink persistence pattern — all of that is correct and reusable as-is.

## Phase 0 — Data audit & foundations (before any agent code)

**Goal:** de-risk the two biggest unknowns before building on top of them.

**Superseded (2026-08-15):** the original plan here was to bulk-import all of `scihub.sql` (~88M rows) into a queryable store and measure DOI-join coverage against `biology_dois.txt` upfront. Tested two parsing approaches (a hand-rolled character-state-machine and a regex-token-stream parser); both were too slow to be worth it (projected 6.5–21 hours for a one-time import). More importantly, it was solving the wrong problem: OpenAlex's live API already returns full metadata (title, abstract, year, journal, OA status) for any topic query, with no local parsing needed at all. Replaced with an **on-demand retrieval design** below — `scihub.sql` is now used only as a targeted, query-time Sci-Hub-availability lookup (confirmed via `grep -F -f` against the full 32.7GB file: ~50-60s per query, I/O-bound on one sequential read, and — because it's I/O-bound — checking one DOI or several hundred from one topic batch costs about the same single pass).

- [ ] **Literature Discovery & Acquisition design:** given a topic/question, (1) discover candidate DOIs + metadata by querying OpenAlex (public, unauthenticated) and PubMed MCP (live) in parallel — no local data needed for this step; (2) for the resulting DOI list, run a targeted `grep -F -f` lookup against `data/scihub.sql` to find which are Sci-Hub-available, extracting DOI/MD5/Filesize only for matches (reuses the row-parser already validated during the superseded approach, applied to the handful of matching lines, not the whole file); (3) full-text acquisition waterfall, in order: OA link (PMC/Unpaywall) → any BYO paywalled/publisher access configured for the org → Sci-Hub (via the MD5 found in step 2) as an explicit, allowed fallback — **user decision, 2026-08-15: Sci-Hub is in scope for the retrieval waterfall, not restricted to metadata-only.** This supersedes the original Gap 9 framing (see below). Still not implemented — becomes a tool in the master agent's roster (Phase 3), not its own agent.
- [x] Stand up Mattermost locally (docker-compose), confirm Bot Accounts + Outgoing Webhooks work with a trivial echo bot — fully done 2026-08-15. `scripts/bootstrap_mattermost.sh` creates admin/team/bot (idempotent, reusable by anyone cloning the repo). Outgoing Webhook end-to-end confirmed. **Note post-pivot: only one bot account is needed going forward** — the echo-bot/Literature-Agent bot becomes *the* bot, not one of several.
- [x] Scaffold the Orchestrator Service — done 2026-08-15. FastAPI skeleton (`orchestrator/app/`), all 9 tables from `06-data-model.md` as SQLAlchemy models (schema unchanged by the pivot — see `06-data-model.md`'s own pivot note), Alembic migration generated+applied+verified against a live Postgres, a Credential Vault module (Fernet encryption), and a Grounding Layer module that structurally enforces the `provenance_type` rule.
- [x] ~~Confirm RxDis still runs standalone post-move~~ — corrected 2026-08-15, then **executed 2026-08-15**: RxDis's code was recovered from git history (`git archive 542b56f src scripts tools testing requirements.txt docker-compose.yml Dockerfile | tar -x -C rxdis/`) into a new top-level `rxdis/` directory. Its `data/Databases`/Supabase path references still need updating before it runs (Phase 3 task, see below) — recovery alone doesn't make it runnable yet.
- [x] **Gap 9 compliance boundary — revised and documented.** Full-text sourcing is allowed to use Sci-Hub as an explicit fallback source, not restricted to OA-only. Requirement: every full-text response must **disclose which tier it came from** (OA / BYO-paywalled / Sci-Hub) — a provenance-labeling requirement, structurally supported via `provenance_type` + `citation_label`.

**Exit criterion — met 2026-08-15.** Phase 0 is complete.

## Phase 1 — First working agent run: Literature/PubMed (Tier 1 · research report Shortlist #9 pattern — shipped on zero new wiring)

**Built and verified under the pre-pivot design — the mechanics are correct and reused going forward; the "one agent per domain" framing they were built under is not.**

- [x] Wire PubMed MCP into the Orchestrator's Claude Code/Codex Runner — done 2026-08-15. Built as an in-process SDK MCP tool (`app/tools/pubmed.py`, real NCBI E-utilities calls) rather than a separate server process. Named `search_articles` to match the tool name already used throughout `docs/`. **This is now the first entry in the master agent's tool roster, not a standalone Literature Agent's only tool.**
- [x] Build the Grounding Layer's core enforcement — done in Phase 0 (`app/grounding.py`), proven for real in Phase 1: `ToolCall` rows persisted per real PubMed search, `GroundingLink` rows point at them, citation precision fixed to intersect what a tool actually returned with what the final answer actually discusses.
- [x] Journey 1 end-to-end, live — verified 2026-08-15 against the real running stack: a real question posted in Mattermost triggered the webhook, the Orchestrator ran a real Claude Code/Codex turn with real PubMed searches, and posted a `grounded` response with 10 real `GroundingLink` rows back into the channel. AC-1/AC-2/AC-4 all hold.
- [x] **Found and fixed a critical isolation bug:** `ClaudeAgentOptions(allowed_tools=[...])` alone does not sandbox a run. Without `setting_sources=[]`, the SDK loads the host's `~/.claude/settings.json` and every personal MCP connector configured there — a real test run used the developer's own personal PubMed/Gmail connectors instead of the intended tool, silently. Fixed; documented in `07-system-architecture.md` as a hard requirement for every agent run.
- [x] Fixed a second bug: `Task.status` was set to `"running"` at creation and never updated. Now transitions to `completed`/`failed`.

**Exit criterion — met 2026-08-15.** Real PubMed calls, real Claude Code/Codex tool use, real grounded response with verifiable citations traced through `Task → ToolCall → Response → GroundingLink`. **Known limitation:** proven on the host venv (inheriting the developer's authenticated `claude` CLI), not the Docker container — containerizing the CLI + non-interactive auth is a distinct packaging task, not yet done.

## Phase 2 — Refactor to the master-agent pattern (do this before adding any more tools)

**Goal:** turn Phase 1's domain-specific proof into the actual product shape — one agent, full roster, visible plan before execution.

- [ ] Generalize `app/claude_runner.py`: replace `run_literature_agent(user_message)` with something like `run_agent(user_message, tool_roster)`, where `tool_roster` is read from the master `AGENT`'s `TOOL_BINDING` rows (currently just PubMed) instead of being hardcoded.
- [ ] Rewrite the system prompt to require the explicit **Plan → Execute → Synthesize** structure (`07-system-architecture.md`, `05-ux-behavior.md` §1): state a methodology naming which tools it intends to use and why, *before* calling any of them.
- [ ] Post the stated methodology as its own message (or leading section of the report) in the Mattermost thread — this is a new, real UX requirement (UX Behavior §1 step 2), not just an internal reasoning step.
- [ ] Update `app/routers/mattermost_webhook.py`: drop the "find any active agent" stub-routing (there's only ever one master `AGENT` now, so this simplifies rather than needing real routing logic) and drop any remaining Literature-specific framing.
- [ ] Re-run Journey 1 against the refactored runner to confirm nothing regressed — same PubMed-only capability, now via the general path instead of a hardcoded one.

**Exit criterion:** the same PubMed question from Phase 1 works through the generalized runner, with the agent's stated methodology visible in the thread before its answer.

## Phase 3 — Grow the tool roster (Tier 1/2 mix) — following the research report's shortlist order

Not "add agents" anymore — each bullet is a tool source added to the one master agent's `TOOL_BINDING` roster. Order still follows the research report's Section 6 (Prioritized Build Shortlist) and Section 9 (Feasibility Check):

- [ ] **ChEMBL + Open Targets** (Shortlist #3/#4) — already-live MCPs, zero new wiring, just add to the roster.
- [ ] **RxDis, as a wrapped tool source** — fix its `data/Databases`/Supabase path references (broken since the `rxdis/` recovery in Phase 0), build the MCP wrapper (trigger pipeline run, poll status, map RxDis's own provenance data into `GROUNDING_LINK` rows), wire progress-update posting (FR-7) if RxDis's FastAPI already emits phase events (check `api/orchestrator.py`).
- [ ] **Literature Discovery & Acquisition** (Phase 0's still-unimplemented design) — OpenAlex + the Sci-Hub targeted-lookup waterfall, as another roster entry alongside the existing PubMed tool.
- [ ] **Ensembl/UniProt/ClinVar/gnomAD** (Shortlist #2) — unlocks Genomics #1/#2/#3/#6/#7/#12/#15/#16. Also wire the **Ontologies domain** here (Gene Ontology, HPO, NCBI Taxonomy, ICD) — flagged in `11-backlog-traceability.md` §5 as genuinely missing, and the natural point to add it since entity normalization matters more as the roster grows.
- [ ] **KEGG/Reactome/STRING** (Shortlist #5; STRING also already present locally in `data/Databases/` — confirm local-data vs. live-API before wiring).
- [ ] **ClinicalTrials.gov/DailyMed/PharmGKB** (Shortlist #6) — pair with Phase 4's review-marker convention from day one.
- [ ] **PDB/AlphaFold DB** (Shortlist #8) — note this is also where Gap 7 (compute) first becomes unavoidable for anything beyond simple structure lookup; defer docking/folding-inference to Phase 6.
- [ ] First BYO-credentialed tool (DrugBank, once RxDis's actual paid dependencies are confirmed against `reference/rxdis-legacy/requirements.txt`) — exercises the Credential Vault (`app/vault.py`, built in Phase 0) for real.

**Exit criterion:** a single query that legitimately needs 2+ of these tools (e.g. "find repurposing candidates for KRAS, then flag ADMET liabilities") produces one thread with a stated multi-tool plan, correct execution across tools, and one synthesized grounded report — this is the real proof of the "puzzle pieces assembled per request" model, not a written scenario.

## Phase 4 — Grounding hardening + first regulatory-adjacent flag

- [ ] Message-attachment structured-output rendering (UX Behavior §3) — needed once reports get complex enough (multi-tool syntheses) that plain text stops being legible.
- [ ] The reserved "requires expert review" visual marker (UX Behavior §4) — triggered by *which tool sources contributed to a response's grounding* (e.g. FAERS, once wired), not by "which agent answered," since there's only one agent. Build and test using Journey 5 as the scenario before the clinical/regulatory tools it depends on are even wired.
- [ ] `#grounding-log` audit channel (FR-10) — the human-facing surface of the `TOOL_CALL` table.

**Exit criterion:** AC-9 passing; the visual-marker convention is documented and enforced in code, keyed on grounding source, not agent identity.

## Phase 5 — Continue growing the roster: remaining Shortlist items + overlooked resources

- [ ] Multi-DB variant consensus capability (Shortlist #7) — once the genomics tools from Phase 3 are wired.
- [ ] Corpus↔PubMed OA cross-reference (Shortlist #10) — the legal prerequisite before any full-text feature is treated as production-ready, per Gap 9.
- [ ] Immunoinformatics tool triage (Shortlist #9) — ships on zero new wiring (local bio.tools notes only), cheap addition to the roster.
- [ ] **Check Hugging Face** (already connected, `07-system-architecture.md`'s compute-layer note) before wiring anything compute-heavy in this phase.

**Exit criterion:** the roster covers a genuinely broad spread of the research report's Section 4 clusters — the point being to prove growing the roster is actually low-friction per the Section 7 wrapping pattern, not that any specific tool count is hit.

## Phase 6 — Compute layer (Gap 7) and the sandboxed tool-runner (Section 7)

Section 7's actual strategy, summarized (full detail in the report, not reproduced here): API-callable tool sources wrap cheaply and need no compute of their own; local CLI/binary tool sources (the majority of the 33,110-entry bio.tools catalog) need a sandboxed execution environment, which is the harder half of this phase. The report's own phasing: (1) wrap the highest-experiment-density, permissively-licensed, API-callable subset first — Immunoinformatics and Cheminformatics; (2) build the sandbox before touching Structural-Biology/Molecular-Dynamics, which get zero benefit from an API-only wrapper; (3) wrap the rest demand-driven, not upfront.

- [ ] Decide buy-vs-build per the research report's Section 9 feasibility rating (Tier 2, procurement blocker) for NVIDIA Platform/cloud GPU vs. the containerized tool-runner (Tier 3, compute-infra blocker) for the CLI/binary bio.tools long tail.
- [ ] First wrap of a Phase-1-priority bio.tools category (Immunoinformatics or Cheminformatics, per Section 7's prioritization table).
- [ ] License-compatibility gate (Section 7) — automated check before any GPL/AGPL-licensed wrapped tool is exposed to a commercial-tier context.

**Exit criterion:** at least one previously-uncallable bio.tools entry is a working roster addition, proving the wrapping pattern generalizes beyond the already-live MCPs.

## Ongoing, not phase-bound

- Containerize the Claude Code/Codex Runner properly (Node.js + `claude` CLI + non-interactive API-key auth in `orchestrator/Dockerfile`) — currently a known Phase 1 limitation, needed before this can run anywhere but the developer's own host.
- Update `researcher-lab-experiment-catalog-2026-08-15.md`'s gap analysis once enough of Phase 3/5's roster growth confirms how much of the report's Tier-2 ratings actually upgrade to Tier-1 given `data/Databases/`'s existing local holdings.
- `CHANGELOG.md` (repo root) — every phase completion and every architecture decision reversal gets an entry.
- The auto-memory project file — kept current with what's actually built vs. planned.

## Related documents

All of `docs/` — this is the plan that ties them together. `11-backlog-traceability.md` for the full report-to-phase mapping. Primary upstream source: [[researcher-lab-experiment-catalog-2026-08-15]].
