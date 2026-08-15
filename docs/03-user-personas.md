# User Personas

Four personas, matched to the academic/commercial split the research report uses throughout Section 4, plus the operator role the platform itself needs.

---

## 1. Priya — Academic Researcher (PhD candidate, computational biology)

**Context:** Third-year PhD student, working on a rare-disease gene-variant project. Comfortable with command-line tools and Jupyter, not a software engineer. Funded by a grant with no budget for commercial database licenses.

**Goals:** Move fast on literature review and variant triage without learning seven different database UIs. Needs citable, traceable output — anything she can't cite in a paper is useless to her, not just unhelpful.

**Pain today:** Manually cross-references ClinVar, gnomAD, and PubMed by hand, copy-pasting between browser tabs. Loses track of which claim came from which source when writing up findings weeks later.

**What she needs from this platform:** The Literature Agent and (once wired) the Genomics Agent's variant-triage flow (Genomics #1/#4 in the research report). Free/public-tier tools only — no BYO-credential setup, she has no budget for paid tools. Grounding matters more to her than speed; a slower, fully-cited answer beats a fast unsourced one.

**Persona-specific requirement this drives:** FR-4/FR-5 (grounding, and explicit "can't ground this" honesty) are non-negotiable for her use case, not a nice-to-have.

---

## 2. Marcus — Commercial/Pharma Researcher (target validation, mid-size biotech)

**Context:** Works on a target-validation team at a biotech with an active drug-discovery pipeline. Has organizational access to ChEMBL, DrugBank, and internal compute, and is used to Schrödinger-class tools. Time-pressured — his team is evaluated on how many targets they can triage per quarter.

**Goals:** Fast, defensible target-prioritization briefs he can bring to a portfolio-review meeting. Needs the platform to handle IP-sensitive compound/target lists without that data leaving the org's own infrastructure — a genuine blocker, not a preference.

**Pain today:** Assembling a target rationale report today means manually pulling Open Targets scores, ChEMBL bioactivity, and literature support into a slide deck by hand — a half-day task for one target.

**What he needs from this platform:** The Drug Discovery Agent (RxDis-backed) and Flagship 5.2 (Literature-Grounded Target Rationale Report), which the research report already flags as ready today with zero new wiring. BYO-credentials for DrugBank/Reaxys once his org decides to license them (FR-6). Higher confidence-scoring bar than Priya — a genetic-association score alone isn't enough, he wants to see the supporting literature, not just a number.

**Persona-specific requirement this drives:** FR-6 (BYO-credential registration) and local-first deployment (compound lists never transit a third-party server) are hard requirements for his org to even approve using this platform.

---

## 3. Dr. Aisha Rahman — Clinical/Regulatory Affairs Lead (large pharma)

**Context:** Not a bench scientist — sits in regulatory affairs, reviews AI-assisted outputs before they inform a submission or safety communication. Legally and professionally accountable for what her team signs off on.

**Goals:** Wants every clinical/regulatory-adjacent output (FAERS signal scans, trial-eligibility drafts, regulatory lit-review sections) to arrive clearly labeled as a draft requiring her review — never something her team could mistake for a validated finding.

**Pain today:** Existing AI tools in this space tend to either overstate confidence or bury the caveats in fine print she has to hunt for.

**What she needs from this platform:** The mandatory-human-review framing from Gap 10 of the research report, enforced structurally (not as a footnote) — this persona is the reason FR-5 and the "research-assistance tool, not autonomous decision-maker" framing exist. She will not be a heavy day-to-day user of the platform herself, but her team's willingness to adopt it depends entirely on this guarantee holding.

**Persona-specific requirement this drives:** Every Clinical/Commercial Pharma Ops agent response (once that cluster is wired) must carry an unmissable "requires expert review" flag — a UX-behavior requirement, not just a data-model field (see `05-ux-behavior.md`).

---

## 4. Operator — the platform administrator (at MVP scale, likely Rohan)

**Context:** Sets up the Mattermost instance, registers bot accounts, wires new MCP tools, and — once Section 8's BYO-credential vault exists — manages per-org credential onboarding. Not a persona the platform's *research* features are designed for, but a persona its *extensibility* model (FR-8) is designed for.

**Goals:** Add a new agent (new MCP source, new bot account) without touching Mattermost's own code or the Orchestrator's core routing logic. Confirm a new agent's grounding behavior works correctly before exposing it to researchers.

**Pain today:** N/A — this role doesn't exist yet; it's being designed into the platform from the start via FR-8.

**What they need from this platform:** A documented, low-friction path to wrap a new tool as an agent (Section 7's wrapping strategy, operationalized). At MVP scale this is a config file + a new MCP server registration, not a full deployment.

---

## Persona-to-requirement map (for traceability during build)

| Persona | Primary FRs | Primary research-report sections |
|---|---|---|
| Priya (academic) | FR-1, FR-2, FR-4, FR-5 | Literature cluster (4.1), Genomics cluster (4.3) |
| Marcus (commercial) | FR-1, FR-3, FR-6, FR-9 | Drug Discovery cluster (4.2), Flagship 5.2 |
| Dr. Rahman (regulatory) | FR-4, FR-5 | Clinical/Commercial cluster (4.6), Gap 10 |
| Operator | FR-8, FR-10 | Section 7 (tool-wrapping), Section 8 (BYO-credential path) |

## Related documents

`04-information-architecture.md` · `05-ux-behavior.md` · `08-cross-feature-journeys.md`
