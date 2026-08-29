# Backlog & Traceability

## Why this document exists

The audit before this doc existed found real gaps: the Build Plan (`10-build-plan.md`) implicitly covers only 2 of 7 domain clusters in detail, 4 of 8 flagship pipelines, 3 of 10 gaps, 6 of 10 shortlist items, about half of Section 8's paid-tool list, none of Section 9's Tier framework as an operational artifact, and none of Section 10's overlooked-resource findings. None of that was a deliberate scope cut — it was 10 focused documents each doing their own job, with no single place tracking whether everything from [[researcher-lab-experiment-catalog-2026-08-15]] had actually been accounted for.

This document is that place. It does not re-describe anything the report already describes in depth — it's a status index, not a duplicate. Every row links back to the report section that has the real detail.

**Status legend:**
- ✅ **Scheduled** — named in a specific Build Plan phase
- 🔜 **Enabled once X lands** — not yet scheduled, but buildable as soon as a specific dependency (an agent, a gap fix) exists; named so a future session knows the actual blocker instead of re-deriving it
- ⏸ **Unscheduled** — no current phase; consult the report section directly when it comes up

---

## 1. Domain clusters (105 experiments, report Section 4)

| Cluster | Count | Status | Note |
|---|---|---|---|
| 4.1 Literature | 12 | 🔜 Partial — MVP Literature Agent (Phase 1) covers #3 (SLR, PubMed-only mode), #9 (Related-Work Generator, Tier 1), #7 (Research-Gap Assistant, needs Open Targets too → Phase 2). Remainder enabled once Phase 0's DOI-join lands. | See `10-build-plan.md` Phase 0/1 |
| 4.2 Drug Discovery | 18 | 🔜 Partial — repurposing pipeline wiring (Phase 2) covers repurposing (#5), overlapping #1–4, #7, #9, #18 (all already Tier 1 per the report). #6, #8, #10–14 need individual MCP wiring not yet scheduled. #15/#16 (patent search, Reaxys) are procurement/legal-gated, not build tasks. | See `10-build-plan.md` Phase 2 |
| 4.3 Genomics | 16 | 🔜 Enabled once Genomics Agent lands (Phase 4) — #1,2,3,6,7,12,15,16 explicitly named. #8 (PRS), #13 (UK Biobank), #14 (HGMD) remain Tier 3 per the report even after wiring — access/compute gated, not just wiring-gated. | See `10-build-plan.md` Phase 4 |
| 4.4 Structural Biology | 15 | ⏸ Unscheduled beyond PDB/AlphaFold DB wiring (Phase 4, unlocks #1 specifically). #5 (docking), #6 (cryo-EM), #11 (MD) need the compute layer (Phase 5) on top of data wiring — two dependencies stacked, not one. | See `10-build-plan.md` Phase 4/5 |
| 4.5 Systems Biology | 16 | 🔜 Enabled once Systems Biology Agent lands (Phase 4) — KEGG/Reactome/STRING wiring unlocks #1, #2, #16 directly per the report. #4, #9 (genome-wide), #13, #14, #15 need real compute (Phase 5), not just wiring. | See `10-build-plan.md` Phase 4 |
| 4.6 Clinical/Commercial | 16 | 🔜 Enabled once Clinical/Commercial Agent lands (Phase 4) — ClinicalTrials.gov/DailyMed/PharmGKB wiring unlocks #1, #4, #5, #9, #10 directly per the report (none DOI-corpus-blocked). #8, #11, #13 additionally need the DOI enrichment from Phase 0. | See `10-build-plan.md` Phase 4 |
| 4.7 Microbiome/Immunology/Model Organisms | 12 | ⏸ Unscheduled — no agent named yet in the Build Plan. #8 (Immunoinformatics Tool Triage) is Tier 1 today (local bio.tools notes only, zero external wiring) and is the cheapest possible next-agent candidate if this cluster gets prioritized before Phase 4's current ordering. | Not in current Build Plan — candidate for re-prioritization |

## 2. Flagship pipelines (8, report Section 5)

| # | Name | Status | Note |
|---|---|---|---|
| 5.1 | Corpus-Grounded Literature Synthesis Engine | 🔜 Partial (Phase 1 PubMed-only mode; full mode needs Phase 0's DOI join) | Referenced in `02-prd.md`, `08-cross-feature-journeys.md` (Journey 1) |
| 5.2 | Literature-Grounded Target Rationale Report | 🔜 Partial (Phase 1/2, PubMed-only mode ships today per the report) | Referenced in `01`, `03`, `08` (Journey 6) |
| 5.3 | Cross-Omics Gene/Pathway Dossier | ⏸ Unscheduled — needs Genomics + Systems Biology + Structural Biology agents (Phase 4) all live | Referenced once in `05-ux-behavior.md` as a rendering example only |
| 5.4 | Variant-to-Literature Diagnostic Workup | ⏸ Unscheduled — needs Genomics Agent (Phase 4); highest-liability flagship in the report, build its human-review UX (`05-ux-behavior.md` §4 pattern) before shipping | Not referenced anywhere in current docs — flagged here for first time |
| 5.5 | Target-to-Lead Virtual Screening Funnel | 🔜 Partial through the ADMET-filter step (Phase 2); docking step needs Phase 5's compute layer | Referenced in `04-information-architecture.md` |
| 5.6 | Immuno-Oncology Target Prioritization Brief | ⏸ Unscheduled — needs a Microbiome/Immunology agent, not currently scheduled (see §1 above) | Not referenced anywhere in current docs — flagged here for first time |
| 5.7 | Competitive & Regulatory Intelligence Dossier | ⏸ Unscheduled — needs Clinical/Commercial Agent (Phase 4) + Drug Discovery's patent-search leg (legal-gated, not just engineering) | Not referenced anywhere in current docs — flagged here for first time |
| 5.8 | Evidence-Quality & Reproducibility Audit | ⏸ Unscheduled — Tier 3 across the board per the report; needs Retraction Watch integration (not cataloged anywhere yet) and author-level corpus enrichment beyond Phase 0's scope | Not referenced anywhere in current docs — flagged here for first time |

## 3. Gap analysis (10 gaps, report Section 3)

| Gap | Status | Note |
|---|---|---|
| 1 — DOI corpus has no metadata | ✅ Resolved differently than planned (Phase 0) | Original plan was bulk-enriching the 16.9M-DOI corpus via a `scihub.sql` join; superseded by on-demand retrieval (OpenAlex/PubMed live discovery per topic, no bulk enrichment needed) — see `10-build-plan.md` Phase 0 |
| 2 — Core genomics DBs unwired | ✅ Scheduled (Phase 4, Genomics Agent) | |
| 3 — Systems biology/pathway tools unwired | ✅ Scheduled (Phase 4, Systems Biology Agent) | |
| 4 — Clinical/commercial regulatory sources unwired | ✅ Scheduled (Phase 4, Clinical/Commercial Agent) | |
| 5 — Structural biology sources unwired | ✅ Scheduled (Phase 4, Structural Biology Agent — PDB/AlphaFold DB leg only) | |
| 6 — CrossRef/Unpaywall/Semantic Scholar/Europe PMC/bioRxiv/medRxiv/Retraction Watch not cataloged | 🔜 Partial — CrossRef/Unpaywall implied by Phase 0's join task; the rest (Semantic Scholar, Europe PMC, bioRxiv/medRxiv, Retraction Watch) are not in any phase | Retraction Watch specifically blocks Flagship 5.8 |
| 7 — No compute/sandbox layer | ✅ Scheduled (Phase 5) | See also §5 below — Hugging Face should factor into this decision, not just NVIDIA/cloud GPU |
| 8 — Access-tier landscape (commercial/controlled-access) | 🔜 Partial — the `CREDENTIAL`/`access_model` schema (Phase 2, first cut) supports this generically, but only DrugBank is actually onboarded; COSMIC/EcoCyc/UK Biobank/etc. have no scheduled onboarding | See §4 below |
| 9 — Full-text sci-hub provenance compliance | ✅ Scheduled (Phase 0), **decision reversed from the report's original stance** — user explicitly decided (2026-08-15) Sci-Hub is an allowed source in the full-text acquisition waterfall, not restricted to OA-only. Requirement is now provenance-*labeling* (disclose OA/BYO-paywalled/Sci-Hub per response), not source-*restriction*. | See `10-build-plan.md` Phase 0's revised Gap 9 task |
| 10 — Regulatory/liability framing | ✅ Scheduled (Phase 3, the review-marker UX convention) | |

## 4. Paid & commercial integrations (13, report Section 8)

| Tool/Platform | Status |
|---|---|
| DrugBank | ✅ First BYO credential onboarded (Phase 2) |
| Reaxys | ⏸ Unscheduled — legal/procurement gated, not a build task |
| HGMD | ⏸ Unscheduled — per-org credential handling designed for in the schema, not yet onboarded |
| COSMIC (commercial tier) | ⏸ Unscheduled |
| EcoCyc (commercial tier) | ⏸ Unscheduled |
| UK Biobank | ⏸ Unscheduled — controlled-access, out of scope until an org formally pursues it (report's own framing, unchanged) |
| OpenAlex (authenticated/bulk tier) | 🔜 Relevant to Phase 0's data-audit task if unauthenticated access proves insufficient for the DOI join |
| CrossRef / Unpaywall (institutional tiers) | 🔜 Relevant to Phase 0 if the local `scihub.sql` join has low coverage and a fallback enrichment pass is still needed |
| NVIDIA Platform (BioNeMo/NIM) | ✅ Named as the "buy" option for Gap 7 (Phase 5) — **see §5, Hugging Face should be evaluated first for lighter-weight needs** |
| General cloud GPU compute | ✅ Named as a Phase 5 option alongside NVIDIA Platform |
| Schrödinger | ⏸ Unscheduled — named in System Architecture as an optional upgrade path, no onboarding planned |
| Certara / Simulations Plus-class | ⏸ Unscheduled |
| Commercial patent-search platforms (Derwent, PatSnap) | ⏸ Unscheduled — relevant to Flagship 5.7 |

## 5. Overlooked resources (report Section 10) — the biggest miss from the original audit

| Finding | Status | Action taken |
|---|---|---|
| **Hugging Face already connected, unused** | 🔜 Now factored into System Architecture's Gap 7 discussion (see the update to `07-system-architecture.md`) — check for a Hugging Face-hosted model before defaulting to NVIDIA/cloud GPU for any Phase 5 compute need | Fixed this pass |
| **AlphaFold Server's non-commercial-only ToS** | 🔜 Flagged as a Phase 4 (Structural Biology Agent) build note — the agent must not route commercial-tier users to AlphaFold Server even though it's free, per the ToS trap the report identified | Fixed this pass — see `07-system-architecture.md` |
| Ontologies (Gene Ontology, MeSH, SNOMED CT, HPO, UMLS, OBO Foundry, NCBI Taxonomy, ICD) | ⏸ Unscheduled — genuinely absent from the Build Plan. Recommend wiring alongside Phase 4's Genomics Agent, since ontology normalization underpins cross-database entity matching (the report's own concern about Flagship 5.3/5.4's entity-mismatch risk) | Not fixed this pass — flagged for Phase 4 planning |
| Workflow orchestration (Galaxy/Nextflow/Snakemake) | ⏸ Unscheduled — becomes relevant once Phase 5's tool-runner starts chaining multiple wrapped tools | Not fixed this pass — flagged for Phase 5 planning |
| RNA-specific databases (Rfam, RNAcentral) | ⏸ Unscheduled — the report itself framed this as "needs an explicit scope decision, not a silent omission." Still undecided. | Open question, not resolved this pass |
| Synthetic biology registries (iGEM, SynBioHub) | ⏸ Unscheduled — low priority per the report's own rating | No action needed yet |
| Commercial chemical vendors (Enamine REAL, MolPort, eMolecules) | ⏸ Unscheduled — relevant to Drug Discovery #12, Flagship 5.5 | No action needed yet |
| ChemRxiv | ⏸ Unscheduled — relevant to Literature cluster's preprint coverage | No action needed yet |
| Toxicology data (EPA ToxCast/Tox21, ToxRefDB) | ⏸ Unscheduled — relevant to Drug Discovery #4/#18 | No action needed yet |
| Real-world/claims data (IQVIA, MarketScan/Optum-class) | ⏸ Unscheduled — relevant to Clinical/Commercial #8; report rated this medium-high priority for the commercial persona | No action needed yet |
| Grant/funding databases (NIH RePORTER, NSF Award Search) | ⏸ Unscheduled — low-medium priority per the report | No action needed yet |

## 6. Feasibility tiers (report Section 9) — now referenced operationally

The report's Tier 1/2/3 rubric wasn't previously tagged onto anything in these docs. Going forward, every new Build Plan checkbox should carry its tier where known — retrofitted onto the current phases below; future phases should be written with the tag from the start rather than added after the fact.

| Build Plan item | Tier (per report) |
|---|---|
| Phase 0 DOI join | Tier 2 (engineering, not access-gated) |
| Phase 1 Literature Agent (PubMed-only) | Tier 1 |
| Phase 2 Drug Discovery Agent (repurposing pipeline + live ChEMBL/Open Targets legs) | Tier 1 |
| Phase 2 DrugBank BYO credential | Tier 2 (procurement, not engineering — per Section 9's blocker-type distinction) |
| Phase 4 Genomics/Systems Biology/Clinical/Structural agents (wiring only) | Tier 2 |
| Phase 5 compute layer (build path) | Tier 3, compute-infra blocker |
| Phase 5 compute layer (buy path — NVIDIA/cloud GPU) | Tier 2, procurement blocker (per Section 9's "buy is faster" framing) |

## Related documents

[[researcher-lab-experiment-catalog-2026-08-15]] (source of truth for every row above) · `10-build-plan.md` · `02-prd.md`
