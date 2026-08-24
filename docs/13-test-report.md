# Test Report — 2026-08-24 pass

Scope: `feature/general-tools` → `test-and-fix` branch. Covers standing up the previously-empty
`orchestrator/tests/`, running the full 233-test per-tool suite plus a new 12-test cross-tool E2E
layer, and fixing what those runs found. See `CONTRIBUTING.md`'s "Running tests" section for how
to reproduce any of this.

## Summary

| Layer | Tests | Result |
|---|---|---|
| Per-tool (`tests/test_*.py`) | 233 | 224 pass; 9 fail, all confirmed external-service flakiness (see Bottleneck 2) — verified via `--forked` full run, which completed cleanly (no process abort) |
| Cross-tool E2E (`tests/e2e/test_combo*.py`) | 12 | All pass |
| **Total** | **245** | |

## Real bugs found and fixed

1. **Process-crashing SWIG runtime conflict — `vina` vs `openbabel`** (found building the E2E
   structure-based-drug-design combo, which chains `vina_docking` → `plip_interactions`, the
   platform's actual core dock-then-analyze workflow).
   `vina` and `openbabel`'s Python bindings are both SWIG-generated; whichever is imported first
   in a process claims the shared SWIG type-registration runtime. The prior import order
   (`vina_docking.py` imported `vina` with no regard for `openbabel`) left `openbabel` — which
   PLIP depends on — with a corrupted runtime. Not a Python exception: an unrecoverable
   `terminate called after throwing an instance of 'swig::stop_iteration'` that aborts the whole
   orchestrator process the next time `plip_interactions` runs, regardless of which tool the agent
   calls first or how much later. **Fix**: `orchestrator/app/tools/vina_docking.py` now imports
   `openbabel` before `vina`, guaranteeing the registration order process-wide since this module
   always loads before any docking call can happen. Verified fixed: `dock_ligand` →
   `profile_ligand_interactions` in sequence, and the full `test_vina_docking.py` +
   `test_plip_interactions.py` + `test_virtual_screening.py` suite, both clean.

2. **OpenAlex 429 flakiness** in `literature_discovery.py`. OpenAlex's anonymous pool
   rate-limits under load ("search cluster under elevated load"); the tool had no retry, so a
   transient rate limit surfaced as a hard tool failure. **Fix**: added a shared `_openalex_get()`
   helper (one retry, respecting OpenAlex's own advertised `retryAfter`, capped at 30s), used by
   all three OpenAlex call sites in `literature_discovery.py`. Confirmed: reduced repeat failures
   from 3/3 to 0/3 in one before/after comparison; sustained rate-limiting beyond one retry still
   happens under heavy load (this pass hit OpenAlex very hard) — see Bottleneck 2.

3. **Inconsistent response contract in `pubmed.py`**. `search_articles`'s success path returns
   both `{"content": [...]}` (MCP text) and `{"articles": [...]}` (structured list, exercised by
   its own test file), but the zero-results early-return only returned `{"content": [...]}` —
   any caller reading `result["articles"]` unconditionally (as the test does) crashes with
   `KeyError` on a query that happens to return zero PubMed hits. Found via a real full-suite run
   hitting exactly that case. **Fix**: the early-return now includes `"articles": []`, matching
   the success path's shape. Verified: `test_pubmed.py` 7/7 pass.

4. Two small carried-over fixes (from reconciling the stranded `test/full-suite` branch, not new
   this pass): Ensembl 404-as-empty-result handling (`ensembl.py`), gnomAD's broader
   "not found"/"invalid" error-message matching (`gnomad.py`).

## E2E layer (new — orchestrator/tests/e2e/)

12 tests, each chaining 3-6 real tools the way the master agent actually would, checking that one
tool's output is genuinely usable as the next one's input (not just that each tool works alone).
Covers every tool in the platform and every research-catalog flagship pipeline that's buildable
from the current tool set (4 of 8 flagships aren't — see Gaps). Every run saves its raw tool
outputs and a pass/fail verdict per hand-off check to `tests/e2e/results/<combo-name>/<timestamp>/`
(gitignored, so this doc is the durable record — check that directory locally for the latest raw
run data).

| # | Combo | What it chains | Status |
|---|---|---|---|
| 1 | Target validation → structural biology | open_targets → uniprot → pdb → alphafold → string_db | ✅ |
| 2 | Drug repurposing / mechanism | chembl → open_targets → clinicaltrials → dailymed → pubmed | ✅ |
| 3 | Variant-to-clinical interpretation | clinvar → gnomad → ensembl → open_targets → pubmed | ✅ (blocked once by a live Ensembl outage — see Bottleneck 2) |
| 4 | Structure-based drug design | uniprot → pdb/alphafold → chembl → vina_docking → plip_interactions → biopandas_structure | ✅ (this is the combo that found bug #1) |
| 5 | Target-to-lead virtual screening funnel | open_targets → chembl → virtual_screening → vina_docking → plip_interactions → soltrannet_solubility | ✅ |
| 6 | Metabolic engineering | kegg → reactome → cobra_fba → equilibrator_thermo → straindesign_intervention | ✅ |
| 7 | Comparative genomics / phylogenetics | ensembl → scikit_bio → phylogenetics → msprime → sourmash_compare | ✅ |
| 8 | Immunoinformatics / epitope design | uniprot → pyhmmer_search → mhcflurry_binding → primer3 | ✅ |
| 9 | Proteomics mass-spec workflow | uniprot → pyteomics_mass → pdb/alphafold → biopandas_structure | ✅ |
| 10 | Enrichment & annotation | open_targets → gene_set_enrichment → gprofiler_enrichment → ontologies → huggingface | ✅ |
| 11 | Literature-grounded synthesis | literature_discovery → pubmed → llm_backend (local model) → grounding.py | ✅ — local Qwen model cited real PMIDs, `grounding.py`'s real rule accepted it |
| 12 | Literature-grounded target rationale | open_targets → chembl → pubmed → llm_backend (local model) | ✅ — matches research catalog §5.2, the flagship flagged as "zero new wiring" |

Combos 11 and 12 ran against the **local LM Studio model** (`qwen/qwen3-4b-thinking-2507`,
`LLM_BACKEND=lm_studio`), not `ANTHROPIC_API_KEY` — no Claude API usage spent on this pass.

## Known bottlenecks

1. **Full single-process test run under memory pressure — SOLVED.** Several tools load real
   native/ML libraries (RDKit, torch, OpenBabel, IQ-TREE); on this machine a plain `pytest` run
   could abort partway through under cumulative memory pressure. **Fix verified**: added
   `pytest-forked` (runs each test in its own subprocess); a full `pytest --forked -m "not e2e"`
   run completed cleanly end to end (224 passed / 9 failed / 2 skipped, zero aborts, 8m12s),
   confirming isolation actually works, not just in theory. This is now the documented way to run
   the full suite (`CONTRIBUTING.md`).

2. **External API flakiness — mitigated, root causes confirmed, both outside our control.** The 9
   remaining failures from the `--forked` run break down as:
   - **6× `literature_discovery` (OpenAlex)**: confirmed via direct `curl` that OpenAlex's own API
     now returns `"Insufficient budget... $0 remaining... Resets at midnight UTC"` —
     this session's own heavy testing exhausted OpenAlex's anonymous-pool daily quota. Not a code
     bug, not fixable by retrying; it self-resolves at UTC midnight. The retry helper added earlier
     (fix #2) still holds for genuinely transient 429s — this is a harder, budget-exhaustion case
     retries can't reach.
   - **1× `ensembl` (`test_default_species_is_human`)** and **1× `ontologies`
     (`test_max_results_clamped_to_fifteen`)**: confirmed via direct `curl` (20s timeout, no
     response) that Ensembl's `/xrefs/symbol/` and EBI OLS's `/search` endpoints are each
     independently slow/degraded for specific queries right now — reproduces outside pytest
     entirely, so it's a live service issue, not our client code.
   - **1× `pubmed` (`test_max_results_is_respected`)**: this was the real bug (fix #3 above), not
     flakiness — already fixed and reverified.
   `pytest-rerunfailures` is now available (`--reruns 2 --reruns-delay 5`) for the genuinely
   transient cases; it cannot and should not paper over a real service outage or a $0 daily
   budget — those need to actually clear.
3. **Global environment mishap during this pass, corrected**: an initial `pip install
   pytest-forked pytest-rerunfailures` resolved to the machine's global `miniforge3` base
   environment instead of the orchestrator's venv (the venv has no `pip` binary — it was created
   by `uv` — so the shell fell through to the global `pip`). This upgraded the base environment's
   `pytest` to 9.1.1 and added the two new packages there. Caught immediately: the two new
   packages were uninstalled from the base environment (restoring it to only what it had before,
   apart from pytest itself), and the packages were correctly reinstalled into the venv via
   `uv pip install --python .venv/bin/python`. **The one thing not fully reverted**: the base
   environment's `pytest` is still 9.1.1 — its exact prior version couldn't be recovered (no pip
   cache, no conda metadata, since it was itself pip-installed into a conda env). If anything else
   on this machine pins an older pytest via that global environment, this is worth knowing about.
4. **Real platform gaps surfaced by building the E2E tests** (documented honestly in each combo's
   own code comments rather than papered over): no sequence-fetch tool (UniProt/Ensembl return
   metadata, not raw sequence, so a real hand-off into pyhmmer/phylogenetics/pyteomics isn't
   buildable yet), no BiGG↔KEGG pathway-ID mapping, no reverse-translation tool. These are product
   scope decisions, not bugs — flagged here for prioritization, not fixed in this pass.
5. **4 of the research catalog's 8 flagship pipelines are still unbuildable**: Cross-Omics
   Gene/Pathway Dossier (needs GTEx/GEO), Immuno-Oncology Target Prioritization (needs cBioPortal),
   Competitive & Regulatory Intelligence Dossier (needs a patent/IP database), Evidence-Quality &
   Reproducibility Audit (needs Retraction Watch + raw-data reprocessing). None of their
   dependencies are wired yet — same status as before this pass, not a regression.
6. **`test-and-fix` isn't merged anywhere.** It's 5 commits ahead of `feature/general-tools`
   (itself ahead of `main`). Nothing pushed or merged — needs explicit sign-off before that
   happens, given how many stale branches already exist from prior attempts at this same test
   consolidation.
