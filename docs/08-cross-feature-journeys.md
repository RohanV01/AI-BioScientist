# Cross-Feature Journeys

**Architecture pivot (2026-08-15):** journeys below reference "the Literature Agent," "the Drug Discovery Agent," and multi-*agent* hand-off (Journey 6) as separate bots coordinating. That's superseded — see `07-system-architecture.md`'s pivot note. There's one agent; what Journey 6 described as cross-agent coordination is now just the one agent's multi-tool execution within a single plan. Journeys 1-5 still hold as scenarios (the tool calls and grounding behavior are unchanged); read "Agent" as "the one agent" throughout, and Journey 4's "which agent" framing as moot.

End-to-end walkthroughs, each exercising multiple components (`04`–`07`) together rather than one feature in isolation. Mapped to research-report flagships where applicable so the journey has a concrete, already-specified target behavior.

---

## Journey 1: Priya asks a literature question (MVP, single-agent)

*Exercises: Message Router, Claude Code/Codex Runner, Grounding Layer, live PubMed MCP.*

1. Priya DMs the Literature Agent: "what's known about variant X in gene Y — any case reports?"
2. Router creates a `TASK`, resolves agent, hands off to the Claude Code/Codex Runner with the PubMed MCP config.
3. Runner calls `search_articles`, `get_article_metadata`; Grounding Layer records each as a `TOOL_CALL` + `GROUNDING_LINK`.
4. Response posts in-thread: synthesized answer with inline `[1][2]` markers, grounding-block attachment listing PMIDs/titles.
5. Priya follows up in the same thread ("what about the 2019 paper specifically?") — same `TASK` thread, new `RESPONSE` row, same grounding discipline.

**Acceptance tie-in:** AC-1, AC-2, AC-4 (`09-test-strategy-acceptance-criteria.md`).

---

## Journey 2: Marcus runs a repurposing scan (MVP, agent wrapping a long-running pipeline)

*Exercises: drug-discovery pipeline MCP wrapper, long-running task progress updates, structured-output rendering.*

1. Marcus, in `#drug-discovery`: `@drug-discovery-agent run repurposing scan for pancreatic cancer, seed genes KRAS TP53`.
2. Agent reacts (receipt confirmation), posts "starting repurposing scan, ~5-10 min".
3. Orchestrator's pipeline wrapper triggers the repurposing run; polls status; posts progress updates per phase transition ("Phase 4: ChEMBL repurposing — docking 42 candidates against KRAS pocket...").
4. On completion, agent posts a summary attachment (top 5 repurposing candidates, docking scores, clinical-stage signal) with a link-out to the full report (PDF-packaging output).
5. Grounding block cites: ChEMBL query IDs, Vina docking run ID, PrimeKG signal — sourced from the pipeline's own provenance data, mapped into `GROUNDING_LINK` rows by the wrapper.

**Acceptance tie-in:** AC-3, AC-5, AC-6.

**Failure branch:** if the pipeline errors mid-run (e.g. a docking step fails), the agent reports the failure and which phase it occurred in — never silently returns a truncated/wrong result as if it were complete (UX Behavior §1 failure behavior).

---

## Journey 3: Marcus needs a BYO-credentialed source mid-task (MVP+, tests FR-6)

*Exercises: Credential Vault, explicit-unavailability UX.*

1. Marcus asks the Drug Discovery Agent for a DrugBank cross-reference on a candidate.
2. Orchestrator checks `TOOL_SOURCE.requires_credential` for DrugBank, finds no `CREDENTIAL` row for Marcus's org.
3. Agent responds: "I don't have a DrugBank credential for this org — an operator can add one in `#operator`. I can still answer using ChEMBL's `drug_search`, which covers most of this." (Graceful degradation per Section 9's fallback tiers, stated explicitly per UX Behavior §1.)
4. An Operator adds the credential (Journey 4).
5. Marcus re-asks; this time the DrugBank leg succeeds, grounding block cites both ChEMBL and DrugBank.

**Acceptance tie-in:** AC-7.

---

## Journey 4: Operator registers a new BYO credential (post-MVP feature, first cut in Phase 2)

*Exercises: Credential Vault write path, encryption, audit trail seed.*

1. Operator, in `#operator`: registers a DrugBank API key for the org.
2. Orchestrator encrypts and stores it (`CREDENTIAL.encrypted_value`), scoped to `org_id`.
3. Confirmation posts back (key never echoed in plaintext, per the requirement in `07-system-architecture.md` that credentials aren't recoverable from logs/traces).
4. `last_used_at` starts populating as agents use the credential — the seed of the audit trail Section 8 calls for.

**Acceptance tie-in:** AC-8.

---

## Journey 5: A regulatory-adjacent flag fires (post-MVP, once Clinical/Commercial cluster is wired)

*Exercises: the human-review UX marker (UX Behavior §4), Dr. Rahman's persona requirement.*

1. A researcher asks the (future) Clinical/Commercial Agent for an adverse-event signal scan (Clinical/Commercial #3 in the research report).
2. Agent runs the FAERS-based disproportionality query, and — because this experiment is explicitly flagged in the research report as "high compliance stakes, human PV review mandatory" — the response posts with the reserved review-required visual marker (distinct attachment color, per UX Behavior §4), and body text explicitly states "unvalidated signal — requires pharmacovigilance review before any action."
3. Dr. Rahman, scanning the channel later, immediately identifies this message via the visual marker without reading every message in full.

**Acceptance tie-in:** AC-9. (This journey is written now, even though the agent doesn't exist yet at MVP, so the UX marker requirement is tested against a concrete scenario rather than left abstract — see `10-build-plan.md` Phase 3.)

---

## Journey 6: A multi-agent flagship pipeline runs (post-MVP, once ≥2 domain agents beyond Drug Discovery/Literature exist)

*Exercises: `TASK.parent_task_id` tree, cross-agent grounding attribution, partial-failure reporting.*

1. A researcher in `#flagship-pipelines` asks for Flagship 5.2 (Literature-Grounded Target Rationale Report) for a named target.
2. Parent `TASK` created; Orchestrator spawns child tasks: one to the Drug Discovery Agent (Open Targets + ChEMBL legs), one to the Literature Agent (PubMed leg).
3. Both children complete; parent aggregates into one thread with sub-headers per agent's contribution, each retaining its own grounding block.
4. **Failure variant:** if the Literature Agent's leg fails (e.g. PubMed rate-limited), the parent response still delivers the Drug Discovery Agent's half, with an explicit note that the literature-grounding leg is missing and why — never silently presents a Drug-Discovery-only answer as if it were the full flagship report.

**Acceptance tie-in:** AC-10.

## Related documents

`05-ux-behavior.md` · `09-test-strategy-acceptance-criteria.md` · `10-build-plan.md`
