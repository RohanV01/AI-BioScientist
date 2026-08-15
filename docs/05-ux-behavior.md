# UX Behavior

Behavioral specification for how the platform actually feels to use, organized by interaction pattern rather than by screen (there are no custom screens at MVP — see `04-information-architecture.md`).

## 1. Delegating a task

**Trigger:** `@agent-name <request>` in a channel, or a DM to the bot.

**Behavior:**
1. The bot immediately reacts to the triggering message (a ✅ or similar Mattermost emoji reaction) to confirm receipt — this happens synchronously, before any tool call, so the researcher isn't left wondering if the message registered.
2. If the task is fast (a live-MCP-only query, e.g. a ChEMBL lookup), the agent replies in-thread within seconds with the grounded answer.
3. If the task is slow (an RxDis pipeline run, a multi-tool flagship pipeline), the agent posts a "starting: <task>, estimated Nm" message, then posts progress updates in the same thread as phases complete (FR-7) — never silence for more than a short interval without an update, even if the update is just "still running phase 3 of 9."
4. On completion, the agent posts the grounded response, using a message attachment for anything structured (see §3).

**Failure behavior:** if a tool call fails (rate limit, unwired source, credential missing), the agent says so explicitly in-thread — "I don't have access to DrugBank for this org — see #operator to register a credential" — never silently falls back to a lower-quality answer without saying so (this is the Section 9 "paid/rate-limited fallback" rule, made visible in the actual UX rather than just a backend policy).

## 2. Grounding — the non-negotiable behavior

Every agent response that makes a factual claim shows its source. Concretely:

- **Inline citation style** for prose claims: `[1]`-style markers in the response text, resolved in a trailing grounding block.
- **Grounding block** (a Mattermost message attachment, not inline text) lists: tool/database called, record ID or DOI, and — where relevant — a confidence/tier note (e.g. "ChEMBL bioactivity, confidence score 9" or "Open Targets association score 0.72, genetic evidence only").
- **No grounding block = the agent must say why.** If an agent gives an opinion, synthesis, or recommendation that isn't a direct tool-call result, it's labeled as such ("based on the above evidence, my assessment is...") rather than presented with the same visual weight as a sourced fact. This distinction is a UX requirement, not just a data-model one — see the `provenance_type` field in `06-data-model.md`.

**Persona tie-back:** this behavior exists because of Priya (needs citable output) and Dr. Rahman (needs to trust the labeling, not hunt for caveats) — see `03-user-personas.md`.

## 3. Structured output rendering

Tables, ranked lists, and dossiers use Mattermost message attachments (fields/fallback-text pattern), not raw markdown tables dumped into chat — markdown tables degrade badly on mobile and in narrow channel widths. Rule of thumb:

- ≤5 rows or a short ranked list → renders directly in the attachment.
- Larger structured output (a full flagship-pipeline dossier, e.g. Flagship 5.3's cross-omics gene dossier) → the attachment shows a summary (top 3–5 findings) plus a link-out to the canvas view (post-MVP; at MVP, link-out is to a plain rendered HTML/markdown file the Orchestrator Service serves locally).

## 4. Human-review flags (Dr. Rahman's requirement)

Any response from a Clinical/Commercial-cluster agent (once wired) carries a **structurally distinct, unmissable visual marker** — not a sentence buried in the response body. Concretely: a dedicated attachment color/icon (Mattermost attachments support a color bar) reserved *only* for "requires expert review" content, never reused for any other purpose, so a regulatory reviewer can visually scan a channel and immediately spot which messages need their sign-off. This is the UX enforcement of Gap 10 from the research report and FR-5.

## 5. Multi-agent (flagship pipeline) delegation

**Trigger:** a request in `#flagship-pipelines`, or an agent recognizing a request exceeds its own domain and proposing a hand-off ("this needs structural data too — should I bring in the Structural Biology Agent?").

**Behavior:** the Orchestrator Service coordinates the multi-agent run behind the scenes; the researcher sees **one thread** with sub-headers per agent's contribution, not a scattered conversation across channels. Each contributing agent's grounding block is preserved and attributed (so a claim from the Structural Biology Agent is distinguishable from one the Drug Discovery Agent made), matching Flagship 5.3's "partial-dossier presentation" failure mode already named in the research report — if one agent's contribution fails or is unavailable, the thread says so explicitly rather than silently omitting that section.

## 6. Onboarding a new researcher

No separate onboarding flow at MVP — the pinned message in each domain channel (`04-information-architecture.md`) is the onboarding surface. A new researcher joining the team sees the channel list, reads the pinned "what this agent can do" message, and starts delegating. This is intentionally minimal for MVP; a richer onboarding experience is out of scope until there's more than two agents to explain.

## 7. Error and edge-case behavior (catalog)

| Situation | Behavior |
|---|---|
| Agent receives a request outside its domain | Suggests the correct agent/channel rather than attempting a bad answer |
| Tool call times out | Says so, offers to retry, does not silently return a partial/stale answer |
| BYO credential missing for a paid-tool step | Names the specific missing credential and points to `#operator` (FR-6) |
| Grounding source becomes unavailable mid-task (e.g. an API goes down) | Reports which part of the answer could not be grounded rather than dropping that section silently |
| Two researchers message the same agent simultaneously | Each gets its own thread; no cross-talk between concurrent tasks |

## Related documents

`03-user-personas.md` · `04-information-architecture.md` · `06-data-model.md` (`provenance_type`, grounding tables) · `08-cross-feature-journeys.md`
