# Changelog

All notable changes to this project are logged here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/); dates in `YYYY-MM-DD`.

## [Unreleased]

### STATUS CHECKPOINT — 2026-08-30, session paused mid-verification (read this first)

**Done and verified, safe to trust:**
- Docker image rebuilt clean (17GB); 10 real build-breaking bugs found and fixed (see the
  "Docker image rebuild" entry below for the full list).
- 15 real tool bugs found and fixed once actually running the real image (BiGG http->https,
  ablang/toxinpred2 permissions, Auto3D's restructured import path, fpocket's wrong output file,
  eigensoft_pca's wrong binary, emboss_water/paml_yn00/blast_search/hpo bugs, DSSP's missing CCD,
  ldsc's own upstream bug) -- full list in the entry below.
- CUDA + `pytest-forked` conflict (7 `mhcflurry_binding` failures) genuinely fixed via a new `gpu`
  pytest marker + a documented two-command test invocation -- verified both directions live.
- Full-suite recheck of everything previously flaky: **39/40 pass clean** in isolation. The one
  holdout, `gwas_catalog`, was independently re-investigated (see its own entry below): confirmed
  via a real direct REST call that this is genuine, current NHGRI-EBI server-side slowness for this
  specific variant (rs7412), not a client-side bug and not fixable by us -- even a bare, unhurried
  solo run hit the full 180s timeout.
- E2E combo recheck inside the real built image: `test_combo16_structural_biology_extras.py` now
  **passes fully** (previously blocked by missing binaries on bare metal -- confirmed fixed now that
  it's running where those binaries actually exist). `test_combo18_cheminformatics_admet.py` failed
  once on a transient container-network blip, then passed cleanly on immediate retry -- not a bug.

**In progress, NOT yet verified or rebuilt -- pick this up next:**
Two more real bugs were found running `test_combo15_metagenomics_pipeline.py` and
`test_combo20_proteomics_and_protein_design.py` against the real image:
1. `checkm2` and `proteinmpnn`'s isolated `uv venv`s (`/opt/checkm2_venv`, `/opt/proteinmpnn_venv`)
   are root-owned -- `uv venv` creates them before the Dockerfile's `USER orchestrator` switch, same
   class of bug already fixed for ablang/toxinpred2's site-packages dirs, just missed these two.
   Real symptom: `PermissionError: [Errno 13] Permission denied: 'checkm2'`.
2. `proteinmpnn`'s installed CLI (`protein_mpnn_run.py`) hard-imports `pkg_resources` at module
   level, but `uv venv` (unlike old-style `virtualenv`) doesn't bundle setuptools into a fresh venv
   by default. Real symptom: `ModuleNotFoundError: No module named 'pkg_resources'`.

**The Dockerfile fix for both is already written** (chown `/opt/checkm2_venv` + `/opt/proteinmpnn_venv`
alongside the existing ablang/toxinpred2 chown step; added `setuptools` to proteinmpnn's `uv pip
install` line) -- but **not yet verified live, and the image has not been rebuilt with it.** Next
steps in order: (a) verify both fixes live in a running container before trusting them, (b)
`docker compose build orchestrator`, (c) re-run `test_combo15_metagenomics_pipeline.py` and
`test_combo20_proteomics_and_protein_design.py` to confirm both now pass, (d) fold this into the
existing "Docker image rebuild" and "real fix for the CUDA" entries below rather than leaving it as
a separate checkpoint note once done.

Nothing in this checkpoint has been committed to git -- everything is still working-tree changes.

### Fixed — 2026-08-30 (real fix for the CUDA + --forked test-harness conflict)
- The full-suite bug pass below found that `mhcflurry_binding`'s 7 tests fail under `pytest
  --forked` with `RuntimeError: Cannot re-initialize CUDA in forked subprocess` -- a real OS/CUDA
  driver rule (CUDA forbids re-initializing a context after `os.fork()`), not a code bug, and not
  something patchable in the tool itself. Added a `gpu` pytest marker
  (`pyproject.toml`) and tagged `test_mhcflurry_binding.py` with it
  (`pytestmark = pytest.mark.gpu`); `proteinmpnn_design`/`protgpt2_generate`'s own test files only
  exercise validation paths, not real in-process torch/CUDA inference, so they didn't need it.
  `CONTRIBUTING.md`'s documented full-suite command is now two invocations
  (`pytest --forked --reruns 2 --reruns-delay 5 -m "not gpu"` then `pytest -m gpu`, no `--forked` on
  the second) -- verified both directions live: the main forked run now correctly deselects all 12
  mhcflurry tests (`--forked -m "not gpu"` -> `12 deselected`), and the separate unforked run passes
  clean (`-m gpu` -> `12 passed`). Any future test that runs real torch/CUDA inference in-process
  should get the same `pytestmark = pytest.mark.gpu`.

### Fixed — 2026-08-30 (Docker image rebuild + full-suite real-environment bug pass)
- Per explicit direction to actually run every test for real rather than report environment gaps,
  rebuilt `aiscientist-orchestrator` from scratch (last built 2026-08-27, stale relative to
  everything added since) and found/fixed 10 real build-breaking bugs along the way, each
  independently confirmed live before moving on: the base image's Debian release moved to `trixie`,
  which dropped `openjdk-17-jdk-headless` from its repos entirely (bumped to `openjdk-21`, confirmed
  javac still supports `-source/-target 8` for BioTransformer's Maven build); USalign's upstream repo
  split its single-file source into several sibling headers (switched the Dockerfile from a raw
  `curl` of `USalign.cpp` to a shallow `git clone` of the whole repo); fpocket's decades-old K&R-era C
  no longer compiles under GCC 14's stricter defaults (`-Wincompatible-pointer-types`/`-Wimplicit-int`
  are now errors even under `-std=gnu99`) -- relaxed via a `CC=` override rather than touching
  fpocket's own code; the ADMIXTURE release tarball's real directory layout didn't match the
  Dockerfile's assumed `dist/` prefix; `checkm2` and `proteinmpnn` each turned out to have a real,
  unresolvable `numpy` pin conflict with `scanpy`/`libroadrunner` respectively -- both are
  subprocess-only CLI tools never imported in-process, so both were pulled out of `requirements.txt`
  and isolated into their own `uv venv`s (checkm2's further needed pinning to Python 3.8 specifically,
  since its own `h5py==2.10.0`/`scikit-learn==0.23.2` pins have no cp311 wheels and fail to build from
  source on 3.11's newer toolchain -- confirmed live that cp38 manylinux wheels exist for both).
- With a real container actually running (not just built), found and fixed 15 more real bugs the
  bare-metal environment could never have surfaced, each verified live against the real tool/API, not
  guessed: `cobra_fba`/`straindesign_intervention` hit BiGG's http->https redirect with no
  `follow_redirects` on the search call (bigg.ucsd.edu now permanently redirects); `ablang_restore`/
  `toxinpred2_toxicity` write into their own site-packages install dir on first use, which is
  root-owned while the container runs as non-root `orchestrator` (chowned just those two package
  dirs); `Auto3D` restructured its package between versions -- `Auto3D.auto3D` moved to
  `Auto3D.entry.auto3D`; `fpocket_detection` parsed the wrong output file entirely (this fpocket
  version no longer embeds `REMARK Pocket` lines in the output PDB -- pocket data moved to a
  separate tab-formatted `_info.txt`, a real parser rewrite, not a regex tweak); `eigensoft_pca`
  called the Debian `eigensoft` package's Perl *wrapper* (`/usr/bin/smartpca`, a completely different
  individual-flags CLI) instead of the real parfile-based binary it actually needs, which lives at
  the separate, unwrapped `/usr/lib/eigensoft/smartpca`; `emboss_water`'s summary regex didn't
  tolerate EMBOSS's own space-padding inside percentage parens (`( 0.0%)`, not `(0.0%)`) for
  low-single-digit values; `paml_yn00` wrote its PHYLIP input with sequence names and sequences on
  separate lines, but yn00's own sequential-format reader requires them on the same line (its own
  error message says so); once that was fixed, yn00's real output row also wasn't the naive
  9-plain-numbers shape the regex assumed -- dN and dS are each a real `value +- SE` pair, matching
  the table's own header; `blast_search` found zero hits even for a 100%-identical reference because
  blastn's default DUST low-complexity filter masked most of a short, repetitive test query --
  disabled DUST for blastn (this tool checks similarity against a caller-supplied reference, not
  NCBI's own public-database use case DUST is meant for); `hpo`'s free-text resolver trusted only the
  raw #1 search hit, but HPO's own API can rank a rare, narrow subtype above the obviously-intended
  broad term for a plain query like "seizure" -- now tries the top 5 ranked candidates and uses the
  first that actually has disease associations; `dssp_secondary_structure` failed on every real PDB
  because `libcifpp-data`'s weekly cron job to fetch the wwPDB Chemical Component Dictionary never
  ran at image build time, leaving `/var/cache/libcifpp/` without `components.cif` at all (baked it
  in directly, same pattern as every other reference-data-at-build-time step in this Dockerfile);
  `ldsc_genetic_correlation` hit a genuine upstream bug in `ldsc.py` itself -- its own top-level
  exception handler calls `traceback.format_exc(ex)`, passing the caught exception positionally into
  an argument that's actually `limit`, which masked what should have been a clean `ValueError: After
  merging with reference panel LD, 0 SNPs remain.` behind a confusing secondary `TypeError` (patched
  with the same one-line-sed technique already used for ToxinPred2's own upstream bug); the tool's own
  "no overlap" detection string also only matched the literal word "No", not ldsc's real "**0** SNPs
  remain" wording, so it would have missed the message even once the traceback bug was fixed.
- Confirmed via live isolation testing, not fixed in code because there's nothing to fix: `mhcflurry`
  (7 of the pytest run's 33 failures) hits a real, general CUDA + `pytest-forked` incompatibility --
  `RuntimeError: Cannot re-initialize CUDA in forked subprocess`, unrelated to this tool's own code
  (passes 12/12 cleanly without `--forked`). Several other failures from the same full run
  (`hunflair_ner`, `soltrannet_solubility`, `clinpgx_annotations`, `ontologies`) turned out to be
  transient resource contention from the machine being under heavy load during that specific run
  (the Docker image build/unpack itself), not real bugs -- each passed cleanly in isolated re-runs.
- 10 new cross-tool E2E combo test files added (`tests/e2e/test_combo13..22_*.py`), covering 60 of
  the 79 tools that had zero E2E hand-off coverage before this session (population genetics,
  metagenomics, structural biology extras, comparative genomics, cheminformatics/ADMET, synthetic
  biology, protein design, antibody/immune repertoire, clinical/regulatory safety, metabolic
  kinetics) -- E2E tool coverage went from 35/114 (31%) to ~95/114 (83%). The remaining ~19 tools
  (R-bridge/DATA-gated: dada2, Seurat, Monocle3, WGCNA, etc.) genuinely can't form a live E2E chain
  without a Docker-hosted R interpreter and file-upload plumbing this pass didn't attempt to add.

### Added — 2026-08-30 (reference-data freshness checking)
- Real per-source live staleness checking for the 8 reference databases baked into the Docker image
  at build time (Kraken2, Kaiju, Bakta, CheckM2, CheckV, LDSC, AMRFinderPlus, PyIR) -- built per
  explicit direction ("can we make it this way that these are constantly checked for releases")
  after confirming none of them auto-update on their own. Each check method was independently
  confirmed live against the real upstream endpoint before being wired in: Zenodo's own
  `/versions/latest` API for Bakta/CheckM2/LDSC (live-confirmed it correctly resolves to a newer
  record when one exists -- LDSC's original record now resolves to a real, different, newer one);
  unauthenticated S3 bucket listing for Kraken2/Kaiju; CheckV's own `CURRENT_RELEASE.txt`; NCBI FTP's
  `latest/` directory listing for AMRFinderPlus. PyIR is self-refreshing (its own `pyir setup`
  command always fetches current data, so there's no separate check step for it).
- New `ReferenceDataSource` table (migration `c4d5e6f7a8b9`), a daily background check
  (`app/main.py`'s lifespan), and `GET /reference-data/status` / `POST /reference-data/check`.
  Live-verified end-to-end against the real dev Postgres, not just written and assumed correct:
  applied the migration, ran the real check against every source, and it correctly flagged exactly
  the one genuinely stale source with `needs_update: true`.
- Scope is deliberately detection + reporting, not automated redownload -- swapping in a newer
  version of a baked DB still means rebuilding the image; documented as an explicit, honest
  boundary rather than a half-built auto-refresh.

### Added — 2026-08-30 (real file-upload pipeline + 8 DATA-gated R-bridge tools -- tool roster 105 -> 114)
- Real Mattermost file-attachment pipeline, unblocking the R-bridge tools Phase 3 explicitly deferred
  for lack of an ingestion path. Confirmed against Mattermost's own server source (not assumed) that
  `OutgoingWebhookPayload` carries a real `file_ids` field and that `GET /api/v4/files/{id}[/info]`
  are real endpoints. `app/file_uploads.py` downloads each attached file into the current
  Experiment's own `uploads/` folder and classifies it by real content inspection (opens archives
  and checks member names rather than trusting the filename). Grounding discipline preserved: upload
  info is surfaced only via a new real tool, `list_uploaded_files` (`experiment_uploads`), never
  injected into the prompt directly.
- Eight DATA-gated R-bridge tools built against that pipeline: `dada2_denoise`, `seurat_analyze`,
  `soupx_correct`, `monocle_pseudotime`, `infercnv_analyze`, `giotto_spatial`,
  `tximport_summarize`, `sleuth_diffexp`. Per the explicit real-time-data requirement, none of them
  bake in a reference snapshot -- `infercnv_analyze`/`tximport_summarize`/`sleuth_diffexp` fetch
  gene/transcript coordinates and tx2gene mappings live from Ensembl (via `biomaRt`) at run time.
  Monocle3 and sleuth install via `remotes::install_github` (not on CRAN/Bioconductor). 33 new
  validation-path tests added (`tests/test_*`); happy-path runs deferred to the batch Docker
  build/test pass, same as every other R-bridge tool (no R interpreter in this sandbox).
- `README.md`'s tool-roster count corrected (105 -> 114); `docs/17`'s Phase 3 section and its
  "DATA-gated, needs a dedicated plan" out-of-scope note both updated to reflect that the file-upload
  path now exists as real infrastructure other DATA-gated tools (BWA, GATK, celltypist, ...) can be
  wired against individually going forward.
- **Still open, not started**: the reference-database freshness-checking work (Kraken2/Kaiju/
  Bakta/CheckM2/CheckV/LDSC/PyIR/AMRFinderPlus are all static, frozen at Docker build time) --
  researched and a concrete architecture validated (Zenodo `/versions/latest`, S3 bucket listing,
  self-update commands, per-source `CURRENT_RELEASE.txt` checks) per explicit user direction to make
  this "constantly checked for releases," but paused mid-investigation to prioritize this
  file-upload batch first; resuming next.

### Added — 2026-08-29/30 (reconsidered rejects, docs/18 platform features, Phase 1.5 GPU tools -- tool roster 97 -> 105)
- Per explicit direction to re-add the important earlier rejects rather than leave them all
  skipped: `poolfstat_fst` (real R package, buildable once the R bridge existed), `pixy_diversity`
  (confirmed live it's real pure Python under a conda-only distribution -- installed from source),
  `toxinpred2_toxicity` (its crash was real, but confirmed the broken code path is never used by the
  model this tool actually calls -- fixed with a one-line documented source patch). RAscore, DDGun,
  GTDB-Tk, and eggNOG-mapper stay rejected with sharper, re-verified reasons (RAscore's fix would
  mean trusting an unvalidated ML stack; DDGun has a second bug plus a heavy HHblits-profile
  requirement; the other two's reference DBs still dwarf the rest of their clusters combined).
- R/Bioconductor bridge extended: `tcga_clinical`, `recount3_search`, `wgcna_modules` -- all real,
  none needing file-upload infrastructure this platform doesn't have.
- Three `docs/18-platform-capability-gaps.md` items built and live-verified against a real running
  Postgres (not just written and assumed correct): auto-generated Methods sections
  (`GET /experiments/{id}/methods`), reproducibility export (`GET /reports/{response_id}/bundle`),
  and a prediction/reality feedback loop (new `prediction_outcome` table + migration, `POST
  /tool-calls/{id}/outcome`, `GET /tool-sources/{name}/track-record`). Found and fixed a real
  pytest-asyncio/asyncpg gotcha along the way (a module-level engine singleton's connection pool
  binding to a stale event loop across tests in the same file).
- Phase 1.5 (local-GPU tools): `nvidia-container-toolkit` installed and GPU passthrough confirmed
  working end-to-end on this host's RTX 3050. `proteinmpnn_design` and `protgpt2_generate` both
  tested live in real GPU containers before being committed -- caught two real, live-only bugs
  (ProteinMPNN's actual CLI flags are hyphenated, not the underscored ones its own PyPI README
  shows; ProtGPT2 via `transformers` was silently ignoring the caller's requested output length).
  `docker-compose.gpu.yml` is a deliberate separate override file so the default `docker compose up`
  still works on any machine without a GPU. RFdiffusion and ChromBPNet investigated and rejected
  with real, live-confirmed reasons (documented in `docs/17`).
- Corrected a stale, never-actually-enforced claim in `requirements.txt`/`pyproject.toml` about
  needing a separate CPU-only torch install -- confirmed live that step never existed in the real
  Dockerfile, and PyPI's plain `torch` wheel already bundles CUDA support by default regardless.
- `README.md`'s tool-roster count corrected (97 -> 105) and a new "Optional GPU passthrough"
  section added to Getting Started.
- **Still open, not started**: Phase 1.6 (NVIDIA NIM hosted inference) needs a real NVIDIA API key
  from the user before it can be built/tested. Several `docs/18` Pass 1/2 items remain genuinely
  unbuilt (no memory across experiments, no research playbooks, no cost/budget visibility, no
  offline/air-gapped mode, no side-by-side comparison structure, no uncertainty propagation across
  chained tool calls, no systematic contradiction detection, no persistent within-experiment
  correction, no adversarial self-check, no staleness disclosure for local bulk data) -- each is a
  real product/architecture decision, not a quick tool-wiring pass, and is left documented rather
  than rushed. All 68 commits from this session are local to this machine, not yet pushed to the
  GitHub remote.

### Added — 2026-08-27/29 (Phase 1/2 completion + R/Bioconductor bridge -- tool roster 37 -> 97)
- Every remaining `docs/17-remaining-tools-wiring-plan.md` Phase 1/2 cluster wired: Immunoinformatics
  (AbLang, PyIR), Cheminformatics (xtb, BioTransformer), Population genetics (GWAS Catalog, EIGENSOFT,
  ADMIXTURE, TreeMix, selscan, LDSC), Sequence analysis (BLAST+, DIAMOND, Clustal Omega, EMBOSS water,
  Prodigal, MUMmer4), Synthetic biology (gibson_assembly, dnachisel), Structural biology (DSSP,
  Foldseek, US-align, FoldMason, Fpocket), Phylogenetics (FastTree, OrthoFinder, PAML yn00,
  ASTRAL-Pro), Metagenomics (Kraken2, Kaiju, Prokka, Bakta, AMRFinderPlus, CheckM2, CheckV, FastANI,
  Barrnap -- 9 of 11; GTDB-Tk/eggNOG-mapper deferred, their reference DBs alone are ~110GB/~11GB).
  Each DB-dependent tool ships the smallest real, still-useful official reference database baked into
  the image at build time (not the largest), keeping the image buildable by any researcher's
  connection/disk rather than only a server-grade one.
- **The R/Bioconductor bridge, decided and built**: `Rscript` subprocess (not `rpy2` -- a real,
  well-known source of production fragility), with `clusterProfiler` (real Bioconductor GO enrichment)
  as the first tool proving the pattern. Recipe documented in `CONTRIBUTING.md`; ~13 more R tools
  scoped in `docs/17` (TCGAbiolinks/recount3/WGCNA are real next candidates; the rest need a real
  file-upload path this platform doesn't have yet).
- Several real, confirmed-live bugs/blockers found and fixed or documented along the way: xtb prints
  its "normal termination" status to stderr, not stdout; FastANI's default fragment length needs a
  genome-scale input, not a short contig; Debian's `prokka`/`igblast` apt packages are respectively
  missing a working `tbl2asn` and the actual `igblastn`/`igblastp` executables entirely (both fixed
  via NCBI's own official binary releases); RAscore/ToxinPred2/DDGun all have genuine, reproducible
  installability/source bugs (dead pinned `tensorflow-gpu`, an unconditional `csv`-module crash, and a
  removed biopython API respectively) -- rejected with the same live-verification rigor as the
  session's earlier HADDOCK3 investigation, not guessed.
- All references to the legacy "RxDis" drug-discovery pipeline removed from planning docs and code
  comments per explicit instruction -- it was never actually wired into any live code.
- `README.md`'s tool-roster count corrected (37 -> 97) to match actual `tool_roster.py` state.

### Added — 2026-08-24/25 (full test suite, live battle-testing, launch-readiness pass)
- Real, live test coverage for the full 37-tool roster: one test file per tool (`orchestrator/tests/test_*.py`, no mocking, hits real external APIs or runs real local computation), plus 12 cross-tool E2E combo tests (`orchestrator/tests/e2e/`) chaining tools the way the master agent actually would. Full findings and known external-API flakiness documented in `docs/13-test-report.md`.
- 12 deliberately hard, adversarial questions run through the real live product (Mattermost -> webhook -> authenticated `claude` CLI agent -> real tool calls), not just direct tool-chain calls -- zero hallucinations across all 12, every real tool limitation disclosed honestly instead of guessed around. Found and fixed 6 real gaps this uncovered (equilibrator/mhcflurry first-use latency bombs, Camofox missing from the compose stack, no coordinate-based ClinVar lookup, no MSA tool, undocumented enrichment library defaults) -- see `docs/15-battle-test-report.md`.
- `docs/16-production-operations.md`: backup/restore procedure, monitoring guidance, and incident runbooks for every real failure mode hit live this pass.
- `docs/14-biotools-shortlist-status.md`: real cross-check of the biotools triage shortlist against actual `tool_roster.py` state (16/~115 shortlisted tools live and verified, not just checked off on paper).
- `uniprot.get_sequence`, `msa` (real MAFFT wrapper), and a `clinvar` coordinate-lookup mode, closing gaps found by the battle-testing pass above.

### Fixed — 2026-08-24/25 (7-item launch-readiness pass, run after the above)
- **Real concurrency bug**: two messages landing in a brand-new Mattermost channel close enough together could both create their own "active" Experiment row, silently splitting that channel's conversation history. Reproduced live (10 concurrent messages -> 3 duplicate rows), fixed with a DB-level partial unique index + retry (migration `a1b2c3d4e5f6`), reproduction now yields exactly 1 row and 0 errors.
- **Real auth bypass**: `MATTERMOST_EXPERIMENT_COMMAND_SECRET` was a real, documented `.env` setting that was never actually passed through to the orchestrator container in `docker-compose.yml` -- meaning the `/experiment` slash command endpoint's token check was silently a no-op in every real deployment, regardless of what a user configured. Fixed, along with the same (lower-severity, non-security) gap for `ORCHESTRATOR_PUBLIC_URL`/`LLM_BACKEND`/`LLM_MODEL`/`LM_STUDIO_BASE_URL`/`LM_STUDIO_CHAT_MODEL`.
- **Dockerfile cache-busting bug**: the equilibrator (1.34GB) and mhcflurry (~164MB) pre-warm downloads sat after `COPY . .`, so any ordinary app-code change re-triggered both downloads on every rebuild, not just the first cold one. Reordered so they only depend on `requirements.txt`.
- **Two "the README just doesn't work" gaps**: `bootstrap_mattermost.py`'s final message printed a descriptive sentence instead of the literal runnable command README promised, and was missing `--bot-token` entirely (without it, the seeded agent can't post replies at all, silently). `seed_dev_data.py`'s `--tools` flag defaulted to `pubmed` only, so the exact command the README told you to copy would seed an agent that could answer exactly one kind of question. Both fixed and verified against a real from-scratch `git clone` + build.
- Stale README sections (the old manual Camofox clone/install workflow, an `/experiment` registration curl example with no way to actually get an admin token, a stale volume name, a wrong step-number cross-reference) rewritten and verified against the real running stack.
- Required credential rotation (`POSTGRES_PASSWORD`, `CREDENTIAL_VAULT_KEY`) made an explicit, documented setup step instead of an easy-to-skip aside.
- `download_paper` tries a direct open-access download first, falling back to Camofox only for genuinely paywalled DOIs -- removes the dependency on Camofox being configured at all for the majority of papers, and gives a distinguishable error message for "Camofox not configured" vs. "Camofox tried and found nothing."
- Working tree cleaned up for handoff: `docs/14-biotools-shortlist-status.md` (previously sitting uncommitted since earlier in the session) committed; personal launch/outreach notes moved to a gitignored `notes/` directory.
- `test-and-fix` (32 commits, everything above) merged into `main` and pushed -- previously all of this work was unreachable by a real `git clone`.

### Changed — 2026-08-24
- **Extracted the legacy drug-discovery pipeline into its own standalone project**, kept in a separate repo with its own history. It's self-contained with no dependency from `orchestrator/` on it, so this doesn't affect the platform.

### Changed — 2026-08-17
- **Containerized the Claude Code/Codex Runner and made setup cross-platform** (Mac/Linux/Windows), closing the "Ongoing" item tracked in `docs/10-build-plan.md`. `orchestrator/Dockerfile` now installs Node.js 20 + the `claude` CLI and runs as a non-root user; the orchestrator no longer depends on a `claude` CLI already installed and authenticated on the developer's own host, which was a real bug found live: the host-run orchestrator had silently drifted to binding `127.0.0.1` instead of `0.0.0.0`, making it unreachable from Mattermost's `host.docker.internal` webhook callback with no error surfaced anywhere. Both Claude auth methods are supported without forcing a switch: `ANTHROPIC_API_KEY` (headless) or a one-time `docker compose exec orchestrator claude login` for a Pro/Max subscription with no API key, persisted in a new `claude_config` Docker volume — `docker-compose.yml` documents both. Replaced `scripts/bootstrap_mattermost.sh` (bash+curl+jq) with `scripts/bootstrap_mattermost.py` (stdlib-only Python), since the SDK itself refuses to run npm's Windows `claude.cmd` shim — native Windows host execution was never viable, so everything now runs in Linux containers via Docker Desktop instead, with `README.md`'s Getting Started section rewritten to match.
- Product renamed from "AI Scientist" to **OpenBioLab** across the README, `CONTRIBUTING.md`, `docs/01-project-goals.md`, `docs/04-information-architecture.md`, `.env.example`, and the orchestrator (`app/main.py`'s FastAPI title, `app/claude_runner.py`'s system prompt and agent-workdir prefix, `pyproject.toml`'s package name, `scripts/seed_dev_data.py`'s default agent name), plus the Docker container names in `docker-compose.yml` and the default Mattermost team name/display name in `.env.example`. The GitHub repo slug (`RohanV01/AI-BioScientist`) was intentionally left unchanged — that's a separate, more disruptive decision (breaks old clone URLs/links) not yet made.
- Closed a real default-credential gap ahead of the repo going public: `.env.example` previously shipped a real-looking default `MM_ADMIN_PASSWORD`, which `scripts/bootstrap_mattermost.sh` used to actually create the Mattermost admin account via the API — anyone who didn't override it got the same known password. Fixed by generating a random password on first bootstrap run (same pattern the script already used for `MATTERMOST_WEBHOOK_SECRET`): written into `.env`, printed once, never a shared default.

### Added — 2026-08-15 (traceability pass)
- `docs/11-backlog-traceability.md` — full status index mapping all 105 experiments, 8 flagships, 10 gaps, 13 paid integrations, and Section 10's overlooked-resource findings from the Researcher's Lab report against actual Build Plan phases. Added after an audit found the original `docs/` suite covered its own MVP scope in real detail but only referenced (not tracked) most of the report's breadth — see "Changed" below for what got fixed as a result.

### Changed — 2026-08-15 (traceability pass)
- `docs/07-system-architecture.md` — added a Compute Layer subsection: check Hugging Face (already connected, previously unused anywhere in these docs) before defaulting to NVIDIA Platform/cloud GPU for Gap 7; added the AlphaFold Server non-commercial-ToS trap as an explicit tool-selection check for the Structural Biology Agent, gated on org tier.
- `docs/10-build-plan.md` — Phase 0 gained an explicit Gap 9 (sci-hub full-text compliance) scoping task, promoted from implicit to concrete now that `data/scihub.sql`'s MD5/Filesize fields make full-text access technically possible, not just metadata; Phase 4's Genomics Agent step now also covers wiring the Ontologies domain (previously absent entirely); Phase 5 expanded with Section 7's actual 3-phase wrapping rationale instead of a bare cross-reference; phase headers tagged with Tier ratings from the report's Section 9.

### Added — 2026-08-15
- Full planning document suite in `docs/`: project goals, PRD, user personas, information architecture, UX behavior, data model, system architecture, cross-feature journeys, test strategy + acceptance criteria, and a phased build plan.
- `README.md` rewritten for the new project direction (Mattermost-based multi-agent messaging platform, superseding the prior single-purpose pipeline README at that path).
- This changelog and the project's auto-memory entry.

### Changed — 2026-08-15
- Repository re-scoped from a single drug-discovery pipeline to a broader multi-agent research platform, per the confirmed product vision in [[researcher-lab-experiment-catalog-2026-08-15]] Section 11.
- Reorganized the folder: legacy pipeline docs/notes moved out to a separate reference location; bulk data (`scihub.sql`, `Databases/`) moved to `data/`.
- `.gitignore` rewritten for the new project structure (data/, node_modules, Go build artifacts, Mattermost runtime config).

### Removed — 2026-08-15
- The legacy pipeline's application code (`src/`, `frontend/`, `scripts/`, `tools/`, `testing/`, `docker-compose.yml`, `Dockerfile`) and its build artifacts (`.venv/`, `.serena/`). Design docs, memory notes, and data were kept separately.

### Discovered — 2026-08-15
- `data/scihub.sql` (32.7GB) turns out to be a full Sci-Hub `scimag` metadata dump (DOI, Title, Author, Year, Journal, PubmedID, PMC per record) — potentially resolves Gap 1 from the Researcher's Lab report (the DOI-biology-classifier corpus having no metadata) via a local join, without rebuilding the CrossRef/Unpaywall enrichment pipeline that report originally proposed. Confirming this is Build Plan Phase 0's first task.
- `data/Databases/` (52GB) already contains local bulk copies of ChEMBL, STRING, GTEx, GWAS Catalog, OMIM, BioGRID, DepMap, PrimeKG, and AlphaMissense — several of these upgrade specific Tier-2 ("needs MCP wiring") gaps from the research report toward Tier-1 ("already have local data"). The research report itself has not yet been updated to reflect this — flagged as an open follow-up in `docs/10-build-plan.md`.

---

## How to use this file

- Every Build Plan phase completion gets an entry.
- Every architecture decision reversal (e.g. if Mattermost gets replaced, if the credential-vault key-management approach changes) gets an entry, even before code exists — decisions are logged when made, not just when shipped.
