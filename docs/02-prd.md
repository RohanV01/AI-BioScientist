# Product Requirements Document

Status: Draft v0.1 · Owner: Rohan · Source of truth for scope decisions until superseded

## 1. Problem statement

A researcher today — academic or commercial — who wants to run a cross-domain research task (e.g. "find the literature-grounded rationale for target X, then check its chemical tractability, then screen known actives for safety liabilities") has to manually operate five to seven separate tools, each with its own UI, auth, and output format, and manually carry context between them. There is no single place to *delegate* a research task and get back a grounded, multi-source answer.

Two things this project has access to make that solvable now that didn't exist as a coherent set before: a large already-cataloged tool inventory (Section 1 of the research report), and a working example of what a fully-orchestrated domain pipeline looks like (RxDis).

## 2. Goals (see `01-project-goals.md` for the full list)

Summarized: make the tool catalog callable via chat delegation, ground every output, stay local-first, extend by wrapping not rewriting, serve academic and commercial users on one product.

## 3. Scope — MVP (Phase 1 of the Build Plan)

**In scope:**
- Self-hosted Mattermost instance as the messaging layer.
- An Orchestrator Service that registers bot accounts per agent, receives delegated tasks via Mattermost's webhook/bot API, invokes Claude Code/Codex with the relevant MCP tools, and posts grounded responses back.
- Two working agents at MVP: a **Literature Agent** (PubMed MCP, already live) and a **Drug Discovery Agent** (wraps RxDis's existing FastAPI endpoints).
- A grounding/provenance layer: every agent response includes a structured citation block (source, record ID, or tool-call reference) rendered as a Mattermost message attachment.
- A minimal BYO-credential store (single-user/single-org scope at MVP — no multi-tenant vault yet) for any paid tool an agent needs.
- The DOI corpus join task: confirm whether `scihub.sql` + `biology_dois.txt` together resolve Gap 1 of the research report.

**Explicitly out of scope for MVP** (see `10-build-plan.md` for phasing):
- The sandboxed tool-runner for the 33,110-tool bio.tools long tail (Section 7, Phase 2 — deferred).
- Multi-org/multi-tenant credential vault security design (Section 8/11 Appendix note — deferred).
- Any agent beyond Literature and Drug Discovery.
- The canvas/side-panel UI for structured output (MVP renders structured output as Mattermost message attachments; a richer canvas is a fast-follow, not MVP).
- Hosted deployment — MVP runs on the researcher's own machine or a single org server.

## 4. Users

See `03-user-personas.md`. Primary MVP persona: the academic/commercial researcher directly delegating tasks. Secondary: the platform operator (likely the same person at MVP scale) standing up agents and credentials.

## 5. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | A user can `@mention` an agent bot in a Mattermost channel or DM and have it receive the message as a task. | P0 |
| FR-2 | The Literature Agent can answer a literature-synthesis question using the live PubMed MCP and return a cited response (Flagship 5.1's PubMed-only mode). | P0 |
| FR-3 | The Drug Discovery Agent can trigger an RxDis pipeline run (e.g. target identification or repurposing for a named disease) and report status/results back into the channel. | P0 |
| FR-4 | Every agent response includes a visible grounding block: what tool/database/record produced each claim. | P0 |
| FR-5 | An agent that cannot ground a claim says so explicitly rather than answering without a source (Section 11's hard rule). | P0 |
| FR-6 | A user or operator can register a BYO credential for a named paid tool (e.g. a DrugBank API key), scoped to their org, without it being visible to other orgs. | P1 |
| FR-7 | Long-running tasks (an RxDis pipeline run can take minutes) post progress updates into the thread rather than going silent. | P1 |
| FR-8 | An operator can add a new agent (register a bot account + wire its MCP tools) without modifying the Orchestrator Service's core message-routing code. | P1 |
| FR-9 | Structured output (tables, ranked lists, dossiers) renders legibly in Mattermost via message attachments, not as a wall of unformatted text. | P1 |
| FR-10 | The system logs which tool calls backed which response, retrievable for audit (foundation for the grounding requirement, and for the eventual credential-usage audit trail from Section 8). | P2 |

## 6. Non-functional requirements

- **Local-first:** the Orchestrator Service, Mattermost, and Postgres run on infrastructure the researcher/org controls. No required outbound calls except to the specific external APIs an agent's task needs (live MCPs, BYO-credentialed paid tools).
- **Resilience of long-running agents:** an RxDis pipeline run failing partway through should not corrupt Mattermost's thread state or leave the user without an error message.
- **Auditability:** every tool call an agent makes should be attributable to the message/task that triggered it (supports FR-10 and the grounding requirement).
- **Extensibility cost:** adding a new MCP-wired data source should not require touching Mattermost's own codebase — Mattermost is a dependency, not a fork (see `07-system-architecture.md`).

## 7. Success metrics

MVP is not being built for a metrics dashboard, but the qualifying bar for "MVP works" is behavioral, listed in `01-project-goals.md`'s "Success looks like" section. Track informally during Phase 1: time-to-first-grounded-response for a literature query, and whether an RxDis run triggered from chat produces the same result as triggering it via its original UI (regression check, not a new metric).

## 8. Open questions

- Does the `scihub.sql` + `biology_dois.txt` join actually cover the 16.9M biology DOIs at useful completeness, or only a subset? (Blocks how much of Gap 1 is actually solved — first Build Plan task.)
- Single Postgres instance shared by Mattermost and the Orchestrator Service (separate schemas), or two instances? Leaning toward one instance / two schemas for local-first simplicity — confirm during Phase 0.
- Where does RxDis's own Supabase dependency go — keep RxDis pointed at its existing Supabase setup initially (fastest path to wrapping it as-is), or migrate it to the shared local Postgres in a later phase? Leaning toward "keep as-is initially" — see `07-system-architecture.md`.

## Related documents

`01-project-goals.md` · `03-user-personas.md` · `06-data-model.md` · `07-system-architecture.md` · `09-test-strategy-acceptance-criteria.md`
