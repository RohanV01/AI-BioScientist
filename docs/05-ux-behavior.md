# UX Behavior

Behavioral specification for how the platform actually feels to use, organized by interaction pattern rather than by screen (there are no custom screens at MVP — see `04-information-architecture.md`).

**Architecture pivot (2026-08-15):** there is one master agent, not one per domain — see `07-system-architecture.md`'s pivot note. Every behavior below is written for that model; the old §5 (multi-agent hand-off) is retired since there's nothing to hand off between anymore.

## 1. Delegating a task — Plan, then Execute, then Synthesize

**Trigger:** `@agent <request>` in any channel, or a DM to the bot.

**Behavior:**
1. The bot immediately reacts to the triggering message (a ✅ or similar Mattermost emoji reaction) to confirm receipt — this happens synchronously, before any planning or tool call, so the researcher isn't left wondering if the message registered.
2. **The agent posts its methodology before doing anything else** — a short, concrete statement of which tools/sources it intends to use and in what order (e.g. "I'll pull KRAS target evidence via Open Targets, search ChEMBL for known actives, then run ADMET on the top candidates"). This is not optional flavor text: it's the visible form of the "puzzle pieces assembled per request" model the platform is built on, and it's what lets a researcher catch a wrong plan before minutes of tool calls run on it.
3. Execution proceeds against that stated plan. If it's fast (a single live-MCP query), the final report can follow within seconds. If it's slow (a multi-step pipeline run, several chained tool calls), the agent posts progress updates in the same thread as steps complete (FR-7) — never silence for more than a short interval without an update.
4. On completion, the agent posts the synthesized, grounded report, using a message attachment for anything structured (see §3).

**Failure behavior:** if a tool call fails (rate limit, unwired source, credential missing), the agent says so explicitly in-thread — "I don't have access to DrugBank for this org — see #operator to register a credential" — never silently falls back to a lower-quality answer without saying so (the Section 9 "paid/rate-limited fallback" rule, made visible in the actual UX rather than just a backend policy). If a step in the stated plan fails partway through, the final report says which step failed and what that means for the rest of the answer — never silently drops it (same principle the old flagship-pipeline "partial-dossier" rule captured, now just a normal execution-failure case for the one agent, not a special multi-agent case).

## 2. Grounding — the non-negotiable behavior

Every agent response that makes a factual claim shows its source. Concretely:

- **Inline citation style** for prose claims: `[1]`-style markers in the response text, resolved in a trailing grounding block.
- **Grounding block** (a Mattermost message attachment, not inline text) lists: tool/database called, record ID or DOI, and — where relevant — a confidence/tier note (e.g. "ChEMBL bioactivity, confidence score 9" or "Open Targets association score 0.72, genetic evidence only").
- **No grounding block = the agent must say why.** If the agent gives an opinion, synthesis, or recommendation that isn't a direct tool-call result, it's labeled as such ("based on the above evidence, my assessment is...") rather than presented with the same visual weight as a sourced fact. This distinction is a UX requirement, not just a data-model one — see the `provenance_type` field in `06-data-model.md`.

**Persona tie-back:** this behavior exists because of Priya (needs citable output) and Dr. Rahman (needs to trust the labeling, not hunt for caveats) — see `03-user-personas.md`.

## 3. Structured output rendering

Tables, ranked lists, and dossiers use Mattermost message attachments (fields/fallback-text pattern), not raw markdown tables dumped into chat — markdown tables degrade badly on mobile and in narrow channel widths. Rule of thumb:

- ≤5 rows or a short ranked list → renders directly in the attachment.
- Larger structured output (a multi-tool synthesis touching several sources — the kind of thing the old "flagship pipeline" concept described, now just what a well-planned single-agent task produces) → the attachment shows a summary (top 3–5 findings) plus a link-out to the canvas view (post-MVP; at MVP, link-out is to a plain rendered HTML/markdown file the Orchestrator Service serves locally).

## 4. Human-review flags (Dr. Rahman's requirement)

Any response whose grounding traces back to a clinical/regulatory-sensitive source (FAERS, trial registries, clinical variant databases — once those tool sources are wired, per `10-build-plan.md` Phase 4) carries a **structurally distinct, unmissable visual marker** — not a sentence buried in the response body. Concretely: a dedicated attachment color/icon (Mattermost attachments support a color bar) reserved *only* for "requires expert review" content, never reused for any other purpose, so a regulatory reviewer can visually scan a channel and immediately spot which messages need their sign-off. This is the UX enforcement of Gap 10 from the research report and FR-5. The marker is triggered by *which tool sources contributed to the grounding*, not by which "agent" answered — there's only one agent now, so this has to be a property of the response's provenance, not the responder.

## 5. Onboarding a new researcher

No separate onboarding flow at MVP — the pinned message in `#town-square` (or wherever the bot is first used — see `04-information-architecture.md`) is the onboarding surface: what the agent can do, roughly what's in its tool roster today, and that the roster grows over time. A new researcher just starts messaging the bot; there's no channel map to learn first.

## 6. Error and edge-case behavior (catalog)

| Situation | Behavior |
|---|---|
| Agent's plan calls for a tool that isn't wired yet | Says so in the plan itself ("I don't currently have access to X for this — here's what I can do instead"), rather than silently omitting that step or attempting it and failing later |
| Tool call times out | Says so, offers to retry, does not silently return a partial/stale answer |
| BYO credential missing for a paid-tool step | Names the specific missing credential and points to `#operator` (FR-6) |
| Grounding source becomes unavailable mid-task (e.g. an API goes down) | Reports which part of the answer could not be grounded rather than dropping that section silently |
| Two researchers message the agent simultaneously (different threads) | Each gets its own thread; no cross-talk between concurrent tasks |
| A stated plan turns out to be wrong once execution starts (e.g. a tool returns nothing useful) | Says so and adapts — reports the revised approach, doesn't silently execute a different plan than the one it showed the researcher without flagging the change |

## Related documents

`03-user-personas.md` · `04-information-architecture.md` · `06-data-model.md` (`provenance_type`, grounding tables) · `08-cross-feature-journeys.md`
