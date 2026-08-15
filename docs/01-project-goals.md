# Project Goals

**Architecture pivot (2026-08-15):** references below to "domain agents" (a Literature Agent, a Drug Discovery Agent, etc.) describe the pre-pivot design. The actual model is **one master agent** with the full tool roster, which plans a methodology per query and executes across whatever tools it needs — see `07-system-architecture.md`'s pivot note. The goals themselves are unaffected; only the "how many bots" framing changed.

## What this is

**AI Scientist** is a local-first research platform: a Mattermost-based messaging workspace where a researcher delegates tasks to specialized domain agents (genomics, drug discovery, literature, structural biology, systems biology, clinical/commercial ops, microbiome/immunology) instead of manually stitching together a dozen databases and tools by hand. Every agent runs on Claude Code/Codex, calling real MCP-wired tools and data sources, and every response carries a traceable link back to the tool call, record, or citation that produced it.

It is the build-out of [[researcher-lab-experiment-catalog-2026-08-15]] (the "Researcher's Lab" report) — that report is this project's requirements source: its 105 experiments are the feature backlog, its gap analysis is the infrastructure roadmap, and its Section 11 (Product Vision) is the architecture brief this document expands on.

## Why this, why now

Three things converged to make this buildable rather than theoretical:

1. **The tool catalog already exists.** ChEMBL, Open Targets, and PubMed are live MCPs today. A 124-resource BioDB registry and a 33,110-entry bio.tools index are already cataloged and ready to be wrapped.
2. **A working drug-discovery agent already exists.** RxDis (`reference/rxdis-legacy/`) is a functioning 9-phase pipeline — target ID, structure validation, repurposing, de novo design, biologics, optimization — that can be wrapped as the platform's first non-trivial agent instead of built from scratch.
3. **The data problem may already be half-solved.** `data/scihub.sql` (32.7GB, a full Sci-Hub `scimag` metadata dump with Title/Author/Year/Journal/PubmedID/PMC per DOI) sat alongside RxDis, undiscovered until this project's kickoff. Joined against the DOI biology classification project's `biology_dois.txt` (16.9M classified biology DOIs), this may resolve the single biggest blocker the research report identified — the DOI corpus having no metadata — without rebuilding the CrossRef/Unpaywall enrichment pipeline the report originally proposed. Confirming this join is the first task in the Build Plan (Section 10, Phase 0).

## Goals

1. **Make the existing tool catalog callable, not just cataloged.** Every experiment in the research report should become something a researcher can actually ask for in a channel, not a line item in a spreadsheet.
2. **One interface for seven domains.** Replace "open five browser tabs and copy-paste between them" with "ask the right agent, get a grounded answer."
3. **Never present an ungrounded claim as fact.** Every agent output traces to a tool call, database record, or citation. This is a hard architectural rule, not a best-effort goal (see [[researcher-lab-experiment-catalog-2026-08-15]] Section 11).
4. **Local-first by default.** Proprietary compound lists, patient-adjacent data (VDJdb repertoires, clinical variant panels), and IP-sensitive queries never have to leave the researcher's own machine or org infrastructure to be processed.
5. **Extend by wrapping, not rewriting.** New capability comes from wrapping an existing tool/database/repo as an MCP server or Mattermost bot, not from reimplementing science tooling that already exists in the 33,110-entry bio.tools catalog or the bio.tools/GitHub long tail.
6. **Serve both personas without forking the product.** An academic researcher on free tools and a commercial/pharma team on licensed tools (Section 8's BYO-credential path) use the same platform, not two different products.

## Non-goals (for now)

- **Not a hosted multi-tenant SaaS.** The MVP is a single-org, self-hosted deployment. Multi-tenant hosting is an explicit future decision, not an MVP requirement (see Appendix of the research report — security/multi-tenancy design is named as unsolved).
- **Not a replacement for wet-lab work.** Every clinical-adjacent or safety-adjacent output is a human-reviewable draft, never an autonomous decision (Gap 10 of the research report).
- **Not building new science tools.** This platform orchestrates and grounds existing tools; it does not implement new docking engines, folding models, or statistical methods.
- **Not real-time collaboration research.** Mattermost's own chat/thread/notification model is used as-is; this project is not reinventing team messaging.

## Success looks like

- A researcher can `@drug-discovery-agent` a target name and get back a literature-grounded rationale report (Flagship 5.2) inside a channel, with every claim citable, in under a few minutes.
- RxDis is reachable as `@drug-discovery-agent run repurposing for <disease>` instead of requiring its own separate UI.
- The DOI corpus enrichment question is answered (solved via local join, or confirmed as still needing the CrossRef/Unpaywall path) within the first week of building, because it gates a large fraction of the rest of the roadmap.
- A second agent (beyond drug discovery) — most likely the literature agent, since PubMed is already live — is delegatable end-to-end, proving the "one interface, many agents" pattern generalizes rather than being a one-off wrapper around RxDis.

## Related documents

[[researcher-lab-experiment-catalog-2026-08-15]] · `docs/02-prd.md` · `docs/07-system-architecture.md` · `docs/10-build-plan.md`
