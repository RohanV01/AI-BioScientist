# Platform Capability Gaps -- Beyond Tool Wiring

`docs/17-remaining-tools-wiring-plan.md` is about adding more data sources and compute tools to
the existing roster. This doc is a different kind of question, asked explicitly from outside that
frame: not "which bio tool is missing" but "what would make this a genuinely better research
platform" -- product and architecture ideas, not another tool to wire in. Two passes, roughly
ordered by how much each would actually change what the product *is* versus what it can look up.

None of this is scoped or sequenced yet -- it's a capture of real gaps worth deliberately deciding
on, the same spirit as `docs/17`'s R/Bioconductor-bridge section: surfaced honestly rather than
silently dropped, not yet a committed roadmap.

## Pass 1 -- product and architecture

1. **No memory across experiments.** Every `Experiment` folder is isolated. If a researcher asks
   about EGFR today and someone else asks about EGFR next month in a different channel, the agent
   has zero awareness the first investigation happened. A real lab accumulates institutional
   knowledge; right now this platform actively forgets. A semantic index over past findings ("has
   anyone here looked at this target before, and what did they conclude") would be a genuinely
   different product, not just another tool.

2. **No feedback loop between prediction and reality.** The platform can compute a docking
   affinity, a solubility prediction, an FBA growth rate -- but there's no mechanism to later
   record "this prediction was validated/contradicted by an actual wet-lab result." Without that
   loop, the system can never get calibrated against ground truth, and users have no way to see
   "how often has this tool's prediction actually held up." This is the difference between a
   lookup engine and something that improves.

3. **No reusable, named research playbooks.** The 12 E2E combos this session validated (target
   validation, drug repurposing, variant interpretation, ...) are currently just things the agent
   *can* do if you phrase a question right. They're not first-class, versioned, invokable
   protocols. A `/playbook target-validation EGFR` that runs a fixed, audited sequence would be
   more reproducible and easier to trust than a freshly-improvised plan every time -- same value
   proposition as a validated SOP in a real lab vs. winging it.

4. **No budget/cost visibility.** This session personally got bitten by OpenAlex's daily budget
   silently running out mid-testing. There's no dashboard showing "you've used X% of today's
   OpenAlex budget" or "this experiment has cost N Claude API calls so far." For anyone running
   this at real scale, that's a real operational blind spot, not a hypothetical.

5. **No reproducibility export.** The whole platform's mission is "every claim traces to a real
   tool call" -- but there's no button that packages everything behind one conclusion (every tool
   call, every input, every citation) into a portable bundle a researcher could attach as
   supplementary material to an actual paper. Right now that trail exists in the DB but isn't
   exportable.

6. **No offline/air-gapped mode.** README already sells "self-hostable, no vendor lock-in" -- but
   pre-patent drug candidate research is often legally barred from touching *any* external API,
   public or not. A mode that runs purely against local compute tools (Vina, COBRApy, MAFFT, etc.)
   and refuses external calls would be a real differentiator for exactly the commercial/pharma
   persona the product already targets, not a hypothetical nice-to-have.

7. **No side-by-side comparison structure.** "Compare these 5 compounds across binding affinity,
   solubility, toxicity, synthesizability" is something the agent can narrate in prose, but there's
   no structured comparison table/ranking as a first-class output -- which matters a lot for an
   actual go/no-go decision, versus a paragraph you have to parse yourself.

## Pass 2 -- trust and scientific rigor

A level deeper than "what's missing" -- "what would make a skeptical scientist actually trust
this."

1. **No retraction detection.** If a cited PubMed paper has since been retracted, nothing checks.
   Retraction Watch has a real, queryable database. This is the single scariest gap for a tool
   whose entire pitch is "grounded, verifiable claims" -- a perfectly-cited, structurally-correct
   `grounded` response can rest on a paper that's since been pulled, and the system would have no
   idea. Worth fixing before almost anything else on either list, because it directly undermines
   the core trust claim.

2. **No uncertainty propagation across chained tool calls.** Combo 5 (target-to-lead virtual
   screening) chains open_targets -> chembl -> virtual_screening -> vina_docking -> plip ->
   soltrannet -- five steps, each with its own real error margin. Nothing tracks or discloses that
   the final answer's confidence is the *compound* of five uncertain steps, not just "this last
   number came from a real tool." A docking score reported with the same apparent confidence
   whether it's step 1 of a chain or step 5 is quietly overstating precision.

3. **No systematic contradiction detection across independent sources.** Battle 12 caught one
   instance of this ad hoc (literature volume vs. genetic association strength for KRAS) because
   the question happened to probe it. But is there a structural habit of the agent actively
   checking "does ClinVar's classification agree with what the literature says" rather than just
   answering whichever tool it happened to call? Right now that discipline lives in one
   well-crafted system prompt paragraph, not in an enforced pattern the way grounding itself is
   enforced in code (`app/grounding.py`).

4. **No persistent within-experiment correction.** Conversation history is flat text (confirmed in
   `_build_conversation_history` -- literally "Researcher: ...\nAgent: ..." strings, no
   structure). If a researcher says "no, use the 2023 dataset, not 2020," that's just more prose in
   the next prompt, hoping the model reads it right, not a tracked constraint the system enforces
   on every subsequent tool call in that experiment.

5. **No auto-generated Methods section.** ~~Every computational biology paper needs a "Methods"~~
   **Built and live-verified 2026-08-29.** `GET /experiments/{experiment_id}/methods`
   (`app/routers/reports.py`, generation logic in `app/methods_report.py`) renders a real Methods
   section for one Experiment: every tool actually invoked (via real `ToolCall` rows, not the full
   tool-roster menu -- a bound-but-never-called tool doesn't appear), call counts, and every real
   record ID it grounded (via `GroundingLink`), plus a separate section for failed/timed-out calls
   excluded from any reported result. Pure DB query + template render, no external network call, no
   new architecture -- same "plain markdown file over HTTP" shape as the existing
   `GET /reports/{response_id}` endpoint. Live-verified against a real running Postgres (not a
   mocked DB): created a real Experiment -> Task -> ToolCall -> Response -> GroundingLink chain,
   generated the section, asserted on its real content, confirmed the unknown-experiment 404 path
   too. Found and fixed a real, previously-latent test-infrastructure gotcha along the way: `app/db.py`'s
   module-level `engine` singleton binds its asyncpg pool to whichever event loop is running when it
   first connects, so a second async DB test in the same file (this was the first file in the suite
   with two) tried reusing connections from the first test's already-closed loop -- fixed with an
   autouse `engine.dispose()` fixture in the test file, not a global pytest-asyncio config change
   that could've had broader side effects on the rest of the suite.

6. **No adversarial self-check before the answer ships.** Right now grounding checks "is there a
   citation," not "is this citation actually being interpreted correctly, or is the reasoning
   connecting citations to conclusion sound." A second pass -- even a cheap one, the same agent
   asked to specifically try to falsify its own conclusion before it's shown to the researcher --
   would catch a class of error grounding structurally can't: correct citations, wrong inference
   from them.

7. **No staleness disclosure for local bulk data.** `data/Databases/` (ChEMBL, STRING, GTEx, etc.)
   are point-in-time snapshots. Nothing tells the researcher "this answer used a 2-year-old local
   copy of X" versus "this hit a live API just now." For anything time-sensitive (a newly
   discovered drug interaction, a newly reclassified variant), that distinction matters and is
   currently invisible.

## Highest-value, lowest-effort starting points

Of both passes, **retraction detection** and **auto-generated Methods sections** stood out: both
were concrete, both were checkable/buildable the same way every tool in `docs/17` already is (a
builder file, a real API or a real DB-table query, a real test), and both attack the platform's
actual stated mission (grounded, publishable, verifiable science) directly, rather than adding
surface area the way one more data source would. **Both are now built and live-verified** -- see
each item's own entry above for details.

**Retraction detection -- built and live-verified 2026-08-26.** `app/tools/retraction_watch.py`'s
`check_retraction_status(pmid|doi)` checks PubMed's own record (`PublicationType == "Retracted
Publication"`, plus `CommentsCorrections RefType="RetractionIn"`/`"ExpressionOfConcernIn"`) --
confirmed live against known-retracted PMIDs (9500320 Wakefield, 24476887 STAP-cell) to be more
reliable than Crossref's `works/{doi}` `update-to` field, which isn't consistently populated for
known-retracted DOIs (checked live, not assumed). **Enforcement is prompt-level, not yet
grounding.py-level**: `MASTER_AGENT_SYSTEM_PROMPT` requires calling this tool on every PubMed-
sourced PMID before it backs a claim, and disclosing retraction/concern status inline rather than
citing it as standing evidence -- live-verified on a real retracted-paper query (Wakefield MMR
paper, PMID 9500320: agent called `pubmed` then `retraction_watch`, response correctly stated
"RETRACTED" and warned against citing it as evidence, `provenance_type` stayed `grounded` with
both PMID 9500320 and the retraction-notice PMID 15016483 as GroundingLinks) and a clean-paper
control query (no retraction, no false positive, both tools still correctly attributed, no
isolation leak). **Still open, deliberately not attempted in this pass**: the harder version this
section originally proposed -- a hard, code-level block in `app/grounding.py` itself that refuses
to let a retracted record back a `grounded` response at all, rather than relying on the agent
following its system prompt. That needs `create_response` to cross-check every citation's
record_ref against retraction status at response-creation time (a live network call inside what's
currently a zero-I/O synchronous enforcement path) -- a real design decision (cache retraction
status? block synchronously? which record types even apply?) worth its own pass, not a corner cut
here.
