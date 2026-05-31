# Project Memory

This file records the practical context from the setup conversation so another assistant can continue without re-discovering it.

## Workspace

- Current working directory: `/home/rohanvyas/Documents/AI Scientist`
- Python virtual environment exists at `.venv`.
- The venv was created with `uv`; verified earlier with Python `3.14.5` and `pip`.
- Main database folder is `Databases/`.
- Keep newly downloaded database files out of the root when possible; move them into relevant `Databases/<source>/` subfolders.

## Key Docs

- Original pipeline spec: `docs/Human Pipeline.md`
- PRDs now present:
  - `docs/MASTER_PRD.md`
  - `docs/PRD_phase0_setup.md`
  - `docs/PRD_phase1_target_id.md`
  - `docs/PRD_phase2_target_validation.md`
  - `docs/PRD_phase3_modality_selection.md`
  - `docs/PRD_phase4_repurposing.md`
  - `docs/PRD_phase5_denovo_small_molecule.md`
  - `docs/PRD_phase6_denovo_biologic.md`
  - `docs/PRD_phase7_mpo.md`
  - `docs/PRD_phase8_validation_gate.md`
  - `docs/PRD_phase9_packaging.md`
  - `docs/PRD_llm_provider_layer.md`

## Database Guidance From The Pipeline Discussion

The Human Pipeline spec says mandatory local downloads are mainly:

- PrimeKG
- DepMap CRISPR matrices
- STRING human network
- GTEx TPM expression
- AlphaMissense human
- A manageable Enamine REAL drug-like subset, not the full 13.6B database

Everything else should usually be API/on-demand unless the user explicitly wants offline mode.

Important advice already given:

- Do not download full Enamine REAL HAC-partitioned files for this laptop setup. Use a smaller "REAL Diverse Drug-Like" or drug-like subset if available.
- Reactome full offline database is not compute-heavy, but is unnecessary initially. Prefer GMT files plus API.
- For BioGRID, the human TAB3 organism file is what the pipeline needs.
- For GTEx, the key file is the gene-level TPM matrix; median TPM by tissue is also useful if downloaded.
- For Human Protein Atlas, the useful files are tissue RNA expression consensus, protein IHC, and optional subcellular protein location. The current HPA files here are small metadata/single-gene files, not the full expression downloads.
- The current GWAS file is a studies file, not the more useful "All associations" file.

## Current Database Inventory

Current `Databases` folder contains extracted/usable files only; no compressed `.zip` or `.gz` archives were found when last checked.

- `Databases/alphamissense/AlphaMissense_hg38.tsv`
- `Databases/biogrid/BIOGRID-ORGANISM-Homo_sapiens-5.0.257.tab3.txt`
- `Databases/chembl/chembl_37.db`
- `Databases/chembl/INSTALL_sqlite`
- `Databases/depmap/CRISPRGeneEffect.csv`
- `Databases/gtex/GTEx_Analysis_2026-05-19_v11_RNASeQCv2.4.3_gene_tpm.gct`
- `Databases/gtex/GTEx_Analysis_2026-05-19_v11_RNASeQCv2.4.3_gene_tpm.parquet`
- `Databases/gwas_catalog/gwas_catalog_v1.0.2.1-studies_r2026-05-16.tsv`
- `Databases/human_protein_atlas/metadata/normal_ihc_tissues.tsv`
- `Databases/human_protein_atlas/metadata/rna_tissue_consensus_tissues.tsv`
- `Databases/human_protein_atlas/metadata/subcellular_locations.tsv`
- `Databases/human_protein_atlas/single_gene_entries/ENSG00000134057.tsv`
- `Databases/primekg/kg.csv`
- `Databases/string/9606.protein.links.detailed.v12.0.txt`

Approximate database folder size after extraction: `49G`.

## Remaining Likely Downloads

These are likely still useful or missing:

- GWAS Catalog "All associations" full list with ontology annotations.
- DepMap `Gene_Dependency_Profile_Summary.csv`, if available.
- Human Protein Atlas full expression/protein TSVs, not only metadata lookup tables.
- GTEx median gene TPM by tissue, optional but handy.
- Reactome GMT gene sets, optional.
- Enamine REAL smaller drug-like/diverse subset, optional later.
- DrugBank XML, only if registered and needed for repurposing.

## Operating Preferences

- Before moving new downloads, inspect root files with `find . -maxdepth 1 -type f`.
- Put each source in a dedicated subfolder under `Databases`.
- Extract only required large archive members when possible, such as only `Homo_sapiens` from BioGRID all-organism archives.
- Keep the workspace root clean.

## PRD + Architecture Session - 2026-05-30

### What was built this session
All PRDs, requirements, and install docs written. No code yet — docs phase complete, build phase starting next.

**Files created:**
- `docs/MASTER_PRD.md` — full architecture, Supabase schema, Celery/Redis, map-reduce pattern, RunConfig schema, Gradio UI spec
- `docs/PRD_llm_provider_layer.md` — pluggable LLM provider interface (cross-cutting, all phases)
- `docs/PRD_phase0_setup.md` through `docs/PRD_phase9_packaging.md` — 10 phase PRDs, each with: Goal, Inputs Required, Process Steps, Local-LLM Decision Points, I/O Contract, Success Criteria, Failure/Recovery
- `requirements.txt` — pip layer
- `environment.yml` — conda scientific stack (Python 3.10)
- `INSTALL.md` — 5-tier install guide

### Architecture decisions (locked)

| Decision | Choice |
|---|---|
| Orchestration | Celery + Redis (4 queues: cpu / gpu / llm / hosted) |
| State & storage | Supabase (Postgres + Storage + Auth + RLS) |
| UI | Gradio (Blocks) |
| API | FastAPI + Pydantic v2 |
| LLM backend | **Pluggable per-user per-run** — Anthropic / OpenAI / Local LM Studio |
| Local LLM | `qwen/qwen3-4b-thinking-2507` via LM Studio (localhost:1234) |
| Python version | **3.10 via conda env `rxdis`** — NOT the existing `.venv` (Python 3.14, incompatible with sci stack) |
| Build order | Sequential M0→M1→M2, then PARALLEL M3/M4/M5, then sequential M6→M7→M8 |

### Key design: Pluggable LLM provider layer
- One provider-agnostic interface (`src/llm/provider.py`) — no phase imports a vendor SDK
- Pipeline reads `provider.capabilities` and adapts map-reduce strategy:
  - Local small model (<16k ctx): chunk + hierarchical tree-merge + 2× self-consistency on critical gates
  - Frontier large model (≥100k ctx): larger chunks + single-pass synthesis
- Cloud LLM token cost counted toward `budget_hosted_usd`; local = $0
- Keys stored encrypted in Supabase (`user_llm_credentials`) or used ephemerally per run

### Key design: Map-reduce pattern (core platform primitive)
Used everywhere LLM must reason over more than fits in context (literature mining, hit lists, ADMET batches):
```
N items → chunk → MAP (local LLM per chunk → llm_chunks table, resumable)
        → REDUCE (tree-merge local OR single-pass frontier)
        → phase_results.output_json
```
Resume: crash at chunk 47 of 500 → restart at 47 (keyed by run_id + task + chunk_index).

### Key design: RunConfig extras Rohan added
Beyond disease/modality/budget: `intent_mode` (explore/repurpose/de_novo gates phases), `seed_targets`, `seed_smiles`, `exclude_targets`, `exclude_drugs`, `tissue_of_interest`, `indication_type`, `selectivity_target`, `resume_from_phase`, `dry_run`, `output_dir`.

### Supabase tables
`profiles`, `projects`, `runs`, `phase_results`, `targets`, `candidates`, `decisions` (with `llm_provider` + `llm_model`), `compute_log`, `llm_chunks`, `user_llm_credentials`

### Celery queues
- `cpu`: DB pulls, NetworkX, RDKit, scoring — high concurrency
- `gpu`: MD, REINVENT4, ProteinMPNN — **concurrency=1** (6 GB GPU singleton)
- `llm`: all LLM calls — 1-2 local, higher for cloud
- `hosted`: NIM, Neurosnap, AF Server, Modal, RunPod — medium concurrency
- Redis token buckets shared across all workers: `nim_rpm` (40/min), `afserver_daily` (30/day)

### Milestone order
```
M0  Infra (Supabase + Redis + Celery + LLM provider + Gradio shell)
M1  Phase 0 + Phase 1   ← NEXT SESSION STARTING HERE
M2  Phase 2 + Phase 3
M3/M4/M5  Phase 4/5/6   ← run in parallel
M6  Phase 7 (MPO)
M7  Phase 8 (validation gate)
M8  Phase 9 (packaging)
```

### Things needed from Rohan before Phase 0/1 code can be written
1. Supabase project URL + service key + anon key
2. Confirm Redis running locally or Docker
3. LM Studio: confirm server running + exact model name shown in UI
4. NCBI API key (PubMed E-utilities, Phase 1)
5. OMIM API key (Phase 1)
6. NIM API key (Phase 0 health check + Phase 2+)
7. Which databases in `Databases/` are fully downloaded vs still in progress

---

## Added Pipeline Tooling Notes - 2026-05-30

The user asked what non-database downloads are needed from `docs/Human Pipeline.md`. Apart from databases, the practical local/software layer is:

- Ubuntu 22.04 / WSL2 with CUDA 12.x.
- Conda scientific environment on Python 3.10; do not rely on the existing Python 3.14 `.venv` for scientific packages.
- Core conda/pip tools: RDKit, OpenBabel, PDBFixer, OpenMM, GROMACS, NetworkX, scikit-learn, pandas, pyarrow, requests-cache, httpx, ratelimit, `gql[all]`, Biopython, pypdb, PyMOL, nglview, REINVENT4, ADMET-AI, chembl webresource client, AutoDock Vina, BoTorch, GPyTorch, gmx_MMPBSA, and boltz.
- Manual/tool downloads: fpocket, ProteinMPNN, ADFRsuite for `prepare_receptor4.py`, NetMHCpan 4.1, TANGO CLI, IUPred3, and optional BindCraft only for A100/large-GPU fallback.
- Other useful add-ons mentioned in the pipeline or follow-up review: node2vec, decoupler-py, gseapy, QuickVina-W/qvina-w, PMX, Docker for ProteomeLM/container workflows, ProLif, MDAnalysis, Meeko, and py3Dmol.
- Hosted/service accounts to prepare: NVIDIA Build/NIM, AlphaFold Server, Neurosnap, HuggingFace, Google Colab, Modal, Replicate, RunPod, Anthropic/OpenAI, ADMETlab 3.0, SwissADME, CLUE/CMap, OMIM, NCBI.

Jupyter_Dock assessment from `AngelRuizMoreno/Jupyter_Dock`:

- Do not treat Jupyter_Dock as a full pipeline replacement.
- It is useful as an optional local docking toolkit/reference notebook layer.
- Good insertion points:
  - Phase 4.3 approved-drug virtual screening: add local backend options `vina`, `smina`, `ledock`, and `qvina-w`.
  - Phase 5.1 large library screening: use qvina-w/QuickVina-W for faster broad screens, especially on RunPod or other rented GPU/CPU instances.
  - Phase 2.3 pocket detection/blind docking: reuse its fpocket-to-per-pocket-docking workflow ideas.
  - Phase 5.6 lead optimization: scaffold-based docking can help when analogs share a known anchor/scaffold.
  - Phase 9/post-docking reporting: ProLif, MDAnalysis, py3Dmol, pose clustering, interaction maps, and score comparisons are useful for reports.
- It should not replace Boltz-2, DiffDock-V2, AlphaFold/AF3, RFdiffusion/BoltzGen, GROMACS/OpenMM/gmx_MMPBSA, ADMET, or target-discovery databases.
- Risk notes: notebook-first, old Python 3.8-ish environment, older Ubuntu-compiled binaries, and fixed relative paths. Prefer extracting ideas/utilities and installing current tools directly.

Clarified role of major modeling/validation tools:

- Boltz-2: complex prediction plus affinity/ranking. Use after Vina/Smina/DiffDock for top-N ligand ranking, biologic/binder-target validation, and optional later affinity checks. Important correction: Boltz-2 can run locally via the official `boltz` package; update mental model to local-first for small/top-N batches with hosted fallback if 6 GB GPU is too small or too slow.
- DiffDock-V2: protein-ligand pose generation/rescoring. Use for top Vina/Smina hits to get better poses/confidence. Keep hosted/NIM for this laptop class.
- AlphaFold / AF3: structure prediction. Use AlphaFold DB and AF2-style hosted tools for protein target structures; use AF3 Server for protein-ligand, protein-DNA/RNA, cofactors, and complex sanity checks. AF3 local is not realistic on 6 GB GPU.
- RFdiffusion: generative protein backbone/binder design. Use in Phase 6.1 as a biologic/peptide design alternative, then sequence with ProteinMPNN and validate with AF/Boltz. Not local on 6 GB.
- BoltzGen: binder/peptide/nanobody/antibody generation. Primary biologic/peptide design route in Phase 6.1. Can be installed locally for smoke tests, but real design-scale runs should be hosted/rented compute.
- GROMACS: molecular dynamics for final pose stability checks on top candidates only.
- OpenMM: lighter Pythonic minimization/short-MD alternative for local sanity checks.
- gmx_MMPBSA: post-processes GROMACS trajectories for MM/PBSA or MM/GBSA binding free-energy estimates; use only after a stable MD trajectory exists.

Pipeline policy update suggested:

- Keep Vina/Smina/QuickVina as cheap first-pass docking.
- Use DiffDock-V2 for pose refinement on top hits.
- Try Boltz-2 locally for top-N ranking first; fall back to Neurosnap/RunPod if local runs fail or are too slow.
- Reserve GROMACS/OpenMM/gmx_MMPBSA for final validation, not broad screening.

---

## Architectural Decision Log — Phase 1 Pivot: NLP → Tabular PU Learning (2026-05-31)

**Decision:** Replace Phase 1's literature-mining map-reduce (old step 1.4) with a
deterministic **tabular Positive-Unlabeled (PU) learning** pipeline over a fused
**STRING Node2Vec + multi-omics** feature matrix, finished by a **decoupleR/DoRothEA**
causal filter. Phases 2–9 are unchanged structurally.

**Status:** Documented (PRD + bottleneck profile rewritten 2026-05-31). Code NOT yet built
— this log records the decision; the old `src/phases/phase1/` literature modules still exist
and will be replaced when the new pipeline is implemented (pending approval of the build plan).

### Why we moved (three reasons)
1. **Hardware / VRAM bottleneck.** A 4B local LLM on a 6 GB RTX 3050 (~2.3 GB free) was a
   single point of failure: ~70 s/call, hundreds of calls per run, frequent OOM/stall
   (run `b71577ef`: B2 dropped 3/4 extraction chunks → 1 gene; B8 ~60–90 s/call; B11 LM
   Studio crashed mid-run). The new pipeline is CPU/RAM-only — **LM Studio can be off**.
2. **Isolating biological novelty (anti-streetlight).** Literature scores reward *how
   well-studied* a gene is, not how promising — biasing against the Tdark/novel targets the
   platform exists to find. PU learning scores genes by **multi-omics signature similarity to
   known validated targets**, surfacing hidden look-alikes regardless of citation count.
3. **Reproducibility.** Local-LLM JSON was unreliable and stochastic; the tabular model is
   seeded and deterministic (identical top-10 across runs).

### What the new Phase 1 is
`disease + known_positives (5–10 validated targets)` → assemble ~20k-gene matrix
[512-d STRING Node2Vec ⊕ DepMap essentiality ⊕ GTEx expression ⊕ AlphaMissense constraint ⊕
optional Harmonizome methylation] → **PU classifier (LightGBM/XGBoost)** scores every gene →
**SHAP** attributions → **DoRothEA** master-regulator (TF) flag → ranked top-N.

### The bottleneck moved
GPU VRAM → **system RAM** (Pandas matrix). New hard rule: merged matrix + transient copies
**well under 10 GB** on the 16 GB box (float32/category dtypes, chunked IO, in-place merges,
parquet caches, `pecanpy` for Node2Vec walks). See `bottlenecks/phase1.md`.

### Downstream impact (Phase 2/3 — verified by reading the code)
Near-zero. Phase 2 re-derives biology from the gene **symbol** and reads only three
`evidence_trail` keys from Phase 1 — `tractability`, `genetic`, `ppi_eigenvector` — plus the
B12 `targets`-upsert fix (`unique(run_id, symbol)`). Phase 3 reads **nothing** from Phase 1
(only Phase 2 output). The new Phase 1 keeps those three keys populated → Phase 2/3 need no
logic change. `tdl`/`modality_hint`/`clinical_stage` are not read anywhere downstream.

### Docs updated for this pivot
- `docs/PRD_phase1_target_id.md` — full rewrite (new data flow; literature/map-reduce removed).
- `bottlenecks/phase1.md` — new RAM-centric bottleneck profile (this architecture).
- `MEMORY.md` — this log.
- `phases/phase1_summary.md` — now describes the *retired* design; refresh when code is rebuilt.
