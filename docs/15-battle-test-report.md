# Battle-Test Report — Live Container, Real Claude Agent, Hard Questions (2026-08-24)

Scope: not unit tests, not direct tool-chain E2E tests (see `13-test-report.md`) — this is 12 real
messages sent through the actual running product (Mattermost → webhook → authenticated `claude`
CLI agent → real tool calls → grounded reply), each deliberately picking a harder, more adversarial
version of the corresponding E2E combo, to see how the agent behaves under genuine pressure before
publishing. Each test ran in its own `/experiment` for a clean context.

## Results

| # | Pipeline | Verdict | Notable finding |
|---|---|---|---|
| 1 | Target validation → structural biology | ✅ PASS | Correctly cross-checked STRING interactors against UniProt's function text, reasoning about *why* each interactor makes biological sense (not just listing them) |
| 2 | Drug repurposing / mechanism | ✅ PASS | Correctly distinguished active vs. completed/terminated trials; honestly flagged that DailyMed's tool output doesn't include indication text, so it couldn't verify label claims |
| 3 | Variant-to-clinical interpretation | ✅ PASS | Discovered `clinvar.search_variants` can't resolve a variant by exact genomic coordinate (gene+term search only) — refused to fabricate a classification, reasoned rigorously about what the gnomAD frequency alone implies instead |
| 4 | Structure-based drug design | ✅ PASS | **Confirms the SWIG vina/openbabel fix holds in production** — this is the exact dock→analyze chain that used to crash the whole orchestrator process |
| 5 | Target-to-lead virtual screening funnel | ✅ PASS | Independently re-docked to confirm reproducibility; correctly identified ASP189 as trypsin's real S1-pocket specificity residue |
| 6 | Metabolic engineering | ⏳ Retried after fix | See "Environment gaps found" below — `equilibrator_thermo`'s first-use dataset download (1.34GB) made the first attempt time out |
| 7 | Comparative genomics / phylogenetics | ✅ PASS (exceptional) | Caught its own suspicious tree result, correctly diagnosed the root cause as a real gap (no MSA tool, so indel-bearing raw sequences broke the tree builder's aligned-input assumption), and correctly trusted the alignment-free MinHash score instead |
| 8 | Immunoinformatics / epitope design | ✅ PASS (after fix) | `mhcflurry`'s model weights weren't installed in the container (downloaded in host testing venv only, never transferred) — agent correctly refused to fabricate binding predictions; fixed live, retried clean with a full 188-peptide ranked scan |
| 9 | Proteomics mass-spec workflow | ✅ PASS | Independently rediscovered the "no sequence-fetch tool" gap from a different angle — refused to claim a peptide is a real ubiquitin substring without being able to verify it |
| 10 | Enrichment & annotation | ✅ PASS | Correctly diagnosed that gseapy vs g:Profiler "disagreement" was a library-scope artifact (GO-only vs. multi-database default), not a real contradiction |
| 11 | Literature-grounded synthesis | ✅ PASS | Camofox (`download_paper`/`read_paper`'s full-text fetcher) failed on every DOI — it's a separate host-level service never added to docker-compose. Agent degraded gracefully to metadata-grounded synthesis with an explicit disclosure, no hallucination |
| 12 | Literature-grounded target rationale | ✅ PASS (exceptional) | Precisely executed the "don't let literature volume overstate association strength" requirement — used real per-indication Open Targets scores to show KRAS's pancreatic-cancer association (0.619) is real but weaker than its RASopathy/NSCLC associations, rather than trading on KRAS's general fame |

**Overall: the agent never hallucinated once across 12 deliberately hard, multi-hop questions.**
Every time a tool had a real limitation (missing data, wrong query shape, failed download, no
alignment tool), it said so explicitly instead of guessing — this is the platform's core grounding
rule working exactly as designed, under real adversarial pressure, not just in a unit test.

## Real bugs/gaps found this pass (in addition to the earlier `docs/13-test-report.md`,
`docs/14-...` items)

1. **`equilibrator_thermo` first-use latency bomb.** Its reference compound database
   (`compounds.sqlite`, 1.34GB from Zenodo) downloads on first real use, not at build time. At
   this network's throughput that's 45-60 minutes — a live user's first metabolic-thermodynamics
   question would appear hung. **Not yet fixed in the Dockerfile** (worked around live by letting
   the download run in the background) — recommend adding a `RUN python -c "..."` step to the
   Dockerfile that pre-warms this cache at build time, same treatment as `mhcflurry` below.
2. **`mhcflurry` model weights not baked into the image.** Downloaded once in the host testing venv
   during earlier pytest runs, but that never transfers into the container (separate filesystem).
   **Fixed live** (`mhcflurry-downloads fetch models_class1_pan` inside the running container,
   ~30s, now persisted in the `orchestrator_home` volume) — same Dockerfile pre-warming
   recommendation as above so this isn't a live surprise on a fresh deployment.
3. **Camofox (paper full-text fetcher) isn't part of the docker-compose stack.**
   `download_paper`/`read_paper` depend on a separate host-level browser-automation service
   (`external/camofox-browser`, `CAMOFOX_API_URL`) that was never containerized here. In this
   deployment, full-text paper reading will always fail — the agent degrades gracefully (confirmed
   in Battle 11), but this is a real feature gap for anyone relying on `read_paper`'s structured
   extraction. Needs either a Camofox service added to `docker-compose.yml` or the gap documented
   explicitly for whoever deploys this next.
4. **`clinvar.search_variants` can't look up a variant by exact genomic coordinate** — gene+term
   search only (confirmed independently in Battle 3). A real capability gap, not a bug: the tool
   does exactly what its interface promises, but that interface doesn't cover this real use case.
5. **No multiple-sequence-alignment (MSA) tool** — `phylogenetics.build_phylogenetic_tree` assumes
   pre-aligned input and has no way to handle raw, indel-bearing real-world sequences (confirmed
   independently in Battle 7). Matches the "no sequence-fetch tool" gap already flagged in
   `13-test-report.md`, and compounds it: even if a sequence-fetch tool existed, two fetched
   sequences still couldn't be aligned before tree-building.
6. **gseapy/gprofiler enrichment default library scopes aren't aligned** (Battle 10) — not a bug,
   but worth a system-prompt nudge or tool-description tweak so the agent (or a user) reaches for
   comparable defaults when asked whether the two tools "agree."

## Launch-readiness recommendation

Given this pass, the **agent's actual reasoning and grounding discipline is launch-ready** — it
held up under genuinely hard, adversarial questions without a single hallucination. What isn't
ready yet is **environment completeness**: items 1-3 above are real gaps between "works in my
testing venv" and "works in a fresh production container," and should be closed (or at minimum
documented as known limitations) before calling this shippable to someone else's machine.
