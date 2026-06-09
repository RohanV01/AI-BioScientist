# RxDis — AI-Native Drug Discovery Pipeline

An open-source, fully local, end-to-end computational drug discovery platform. RxDis takes a disease name + a handful of known target genes and runs a 9-phase pipeline — from target identification through de novo molecule generation, biologics design, multi-parameter optimization, and candidate packaging — entirely on your own hardware.

No cloud API required. No vendor lock-in. Every LLM gate can run on a local model via LM Studio.

---

## What It Does

```
Disease + seed genes
        │
        ▼
Phase 0  Health check (databases, credentials, cost estimate)
Phase 1  Target identification — PU learning on 14 omics features
Phase 2  Target validation — structure, druggability, pockets, variants
Phase 3  Modality routing — SM / biologic / PROTAC / repurpose
        │
   ┌────┴────────────────┐
   ▼                     ▼
Phase 4  Drug repurposing   Phase 5/6  De novo design
(ChEMBL + Vina docking)   (REINVENT4/BRICS + RFdiffusion + ProteinMPNN)
   └────────────────────┘
                │
                ▼
Phase 7  Multi-parameter optimization (Pareto + GP surrogate)
Phase 8  Validation gate (triple Vina re-dock, 6-axis scorecard)
Phase 9  Packaging (PDF report, citations, reproducibility bundle)
```

The UI is a React/Vite SPA that streams live phase events, shows every LLM decision with full prompt/response, and renders SHAP attributions, docking poses, and Pareto fronts.

---

## Screenshots

> The pipeline studio after a completed run on pancreatic cancer (KRAS/TP53).

*(Add screenshots here)*

---

## Key Features

| Feature | Detail |
|---|---|
| **Local-first** | All databases downloaded once; runs fully offline. LM Studio for local LLM. |
| **Pluggable LLM** | LM Studio (default) · Anthropic Claude · OpenAI GPT-4o — swap per run |
| **Full provenance** | Every LLM gate shows prompt, raw response, and parsed decision |
| **SHAP attributions** | Phase 2 druggability scores fully explained per feature |
| **Repurposing** | 3-signal triangulation: Vina docking + clinical stage + PrimeKG KG signal |
| **De novo SM** | REINVENT4 Mol2Mol → BRICS fallback; seeded from Phase 4 repurposing hits |
| **Biologics** | RFdiffusion backbone → ProteinMPNN sequence design → developability filter |
| **NetMHCpan** | Real MHC-I immunogenicity prediction for peptide candidates |
| **MPO** | GP surrogate active-learning loop; Pareto-front ranking with hypervolume |
| **Celery / thread** | Runs in a background thread (no Redis) or Celery workers (parallel P4/P5/P6) |
| **Supabase** | Multi-tenant state, run history, candidate storage |

---

## Architecture

```
frontend/          React 18 + Vite + TypeScript SPA
src/
  api/             FastAPI (main.py, orchestrator.py)
  config/          RunConfig, settings (all DB paths)
  db/              Supabase client, schema, run_state helpers
  llm/             Provider abstraction (LM Studio / Anthropic / OpenAI)
  phases/
    phase0/        Health checks, cost estimate
    phase1/        PU model, Open Targets, genetic evidence, STRING PPI
    phase2/        Structure (AFDB/RCSB), pockets (fpocket), SHAP druggability
    phase3/        Modality rule engine, LLM routing gate
    phase4/        ChEMBL repurposing, Vina docking, PrimeKG, LINCS
    phase5/        REINVENT4/BRICS generation, Ro5/ADMET filters, Vina
    phase6/        RFdiffusion, ProteinMPNN, developability, NetMHCpan
    phase7/        Pareto front, GP surrogate, hypervolume
    phase8/        Triple Vina re-dock, 6-axis scorecard
    phase9/        PDF assembly, citations.bib, Supabase upload
  workers/         Celery tasks (cpu / llm / gpu / hosted queues)
Databases/         Local copies of all scientific databases (see below)
tools/             ProteinMPNN (git clone), RFdiffusion (git clone)
```

---

## System Requirements

- **OS:** Linux (Ubuntu 22.04+ recommended) or macOS
- **Python:** 3.10 (required — RDKit/OpenMM don't build on newer versions)
- **RAM:** 16 GB minimum; 32 GB recommended for full pipeline
- **GPU:** Optional but recommended for RFdiffusion (6 GB+ VRAM). Everything else runs on CPU.
- **Disk:** ~80 GB for all databases + model weights

---

## Installation

### Step 1 — Conda scientific base

```bash
# Install Miniforge if you don't have conda
curl -L https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh | bash

conda env create -f environment.yml      # creates 'rxdis' env on Python 3.10
conda activate rxdis
```

This installs RDKit, OpenMM, pdbfixer, fpocket build dependencies, and OpenBabel.

### Step 2 — Pip layer

```bash
pip install -r requirements.txt
playwright install chromium
```

### Step 3 — Git-cloned tools

These cannot be pip-installed. Clone them into the `tools/` directory:

```bash
mkdir -p tools

# ProteinMPNN (Phase 6 sequence design)
git clone https://github.com/dauparas/ProteinMPNN tools/ProteinMPNN
# Download weights (v_48_020.pt is used by default — already in the repo)

# RFdiffusion (Phase 6 backbone generation — GPU recommended)
git clone https://github.com/RosettaCommons/RFdiffusion ~/tools/RFdiffusion
cd ~/tools/RFdiffusion && pip install -e .
# Download model weights:
bash scripts/download_models.sh
# Create dedicated conda env for RFdiffusion (needs Python 3.12 + CUDA torch + DGL):
conda create -n rfdiffusion python=3.12
conda activate rfdiffusion
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install dgl -f https://data.dgl.ai/wheels/repo.html
pip install -e ~/tools/RFdiffusion
```

### Step 4 — NetMHCpan (academic licence, free)

Required for real MHC-I immunogenicity prediction in Phase 6.3.

1. Register at https://services.healthtech.dtu.dk/services/NetMHCpan-4.2/
2. Download the Linux package
3. Extract to `~/netMHCpan-4.2/`
4. The pipeline auto-detects it at that path.

### Step 5 — AutoDock Vina binary

```bash
# Pre-built binary (Linux x86_64)
wget https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.7/vina_1.2.7_linux_x86_64 \
    -O ~/.local/bin/vina && chmod +x ~/.local/bin/vina
```

### Step 6 — Databases

Download all required databases into the `Databases/` directory. The pipeline reads from:

| Database | Path | Download |
|---|---|---|
| ChEMBL 35 | `Databases/chembl/chembl_35.db` | [chembl.ebi.ac.uk](https://chembl.ebi.ac.uk/downloads/) — SQLite |
| PrimeKG | `Databases/primekg/` | [Harvard Dataverse](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/IXA7BM) |
| Open Targets (genetics) | `Databases/` | [Open Targets FTP](https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/) |
| DepMap (Chronos) | `Databases/depmap/` | [depmap.org](https://depmap.org/portal/data_page/) — `CRISPRGeneDependency.csv` |
| STRING v12 | `Databases/string/` | [string-db.org](https://string-db.org/cgi/download) — `9606.protein.links.v12.0.txt.gz` |
| GTEx v10 | `Databases/gtex/` | [gtexportal.org](https://gtexportal.org/home/downloads/adult-gtex/bulk_tissue_expression) |
| AlphaMissense | `Databases/alphamissense/` | [Google DeepMind](https://github.com/google-deepmind/alphamissense) — `AlphaMissense_aa_substitutions.tsv.gz` |
| Human Protein Atlas | `Databases/human_protein_atlas/` | [proteinatlas.org](https://www.proteinatlas.org/about/download) — `proteinatlas.tsv.gz` |
| GWAS Catalog | `Databases/gwas_catalog/` | [ebi.ac.uk/gwas](https://www.ebi.ac.uk/gwas/docs/file-downloads) |
| OMIM | `Databases/omim/` | Academic access at [omim.org](https://www.omim.org/downloads) |
| DoRothEA (TF regulons) | `Databases/dorothea/` | [Bioconductor](https://bioconductor.org/packages/dorothea) or CARNIVAL export |
| BioGRID | `Databases/biogrid/` | [thebiogrid.org](https://downloads.thebiogrid.org/BioGRID) — MITAB format |

### Step 7 — Supabase

```bash
# Option A: Supabase Cloud (free tier works)
# 1. Create project at supabase.com
# 2. Copy .env.example to .env, fill SUPABASE_URL and SUPABASE_SERVICE_KEY

# Option B: Local Supabase (Docker)
npx supabase init
npx supabase start
# Copy the local URL/key into .env

# Run the schema migration
psql "$DATABASE_URL" < src/db/schema.sql
```

### Step 8 — Local LLM (LM Studio)

```bash
# 1. Download LM Studio from https://lmstudio.ai
# 2. Load model: qwen/qwen3-4b-thinking-2507  (4 GB, runs on CPU)
#    Or any OpenAI-compatible model server
# 3. Start the local server (listens on http://localhost:1234/v1)
```

### Step 9 — Environment file

```bash
cp .env.example .env
# Edit .env:
#   SUPABASE_URL=...
#   SUPABASE_SERVICE_KEY=...
#   REDIS_URL=redis://localhost:6379/0   (if using Celery)
#   RFDIFFUSION_DIR=~/tools/RFdiffusion  (optional override)
```

---

## Running

### Development (no Redis, single process)

```bash
conda activate rxdis

# Terminal 1: API
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

The orchestrator falls back to a background thread when Redis is unavailable. Phases run sequentially. Good for development and single-machine use.

### Production (Celery workers, parallel P4/P5/P6)

```bash
# Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# Start workers (separate terminals or systemd services)
celery -A src.workers.celery_app worker -Q cpu   -c 4 -n cpu@%h   --loglevel=info
celery -A src.workers.celery_app worker -Q llm   -c 2 -n llm@%h   --loglevel=info
celery -A src.workers.celery_app worker -Q gpu   -c 1 -n gpu@%h   --loglevel=info

# Start API
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 2

# Optional: Flower dashboard at http://localhost:5555
celery -A src.workers.celery_app flower
```

### Docker Compose (quickest start)

```bash
# Build and start everything
docker compose up -d redis
docker compose up api worker-cpu worker-llm

# With GPU support
docker compose up worker-gpu
```

---

## Running a Pipeline

1. Open http://localhost:5173
2. Click **New Experiment**
3. Fill in:
   - **Disease name** — e.g. "Pancreatic Ductal Adenocarcinoma"
   - **EFO ID** — e.g. `EFO_0002618` (lookup at [ebi.ac.uk/efo](https://www.ebi.ac.uk/efo/))
   - **Seed targets** — known positive gene symbols: `KRAS`, `TP53`, `SMAD4`
   - **Seed SMILES** *(optional)* — known active compounds to prime de novo generation
   - **Intent mode** — Explore / Repurpose / De Novo
   - **Run through phase** — 1 (target ID only) through 8 (full pipeline)
4. Click **Launch Pipeline**

The UI streams live phase events. Click any phase panel to inspect targets, candidates, LLM decisions, and scores.

---

## Intent Modes

| Mode | Phases | Use when |
|---|---|---|
| **Explore** | 0→1→2→3→4→5→6→7→8→9 | You want the full pipeline: targets + repurposing + de novo |
| **Repurpose** | 0→1→2→3→4→7→8→9 | You want to find existing drugs for new targets |
| **De Novo** | 0→1→2→3→5→6→7→8→9 | You want to design new molecules/biologics from scratch |

---

## Phase Reference

### Phase 0 — Health Check
Validates all database files, credentials, and tools. Produces a go/no-go decision and cost estimate before committing compute.

### Phase 1 — Target Identification
- Pulls disease-gene associations from Open Targets, GWAS Catalog, OMIM, DISEASES
- Builds a 14-feature evidence matrix per gene (genetic, expression, essentiality, network, pathway, literature)
- Runs bagging Positive-Unlabelled (PU) XGBoost to score the proteome
- DoRothEA transcription factor activity as final regulatory filter
- Output: ranked list of candidate targets with PU score and SHAP attributions

### Phase 2 — Target Validation
Per target: AlphaFold/RCSB structure retrieval → fpocket binding site detection → AlphaMissense variant pathogenicity → GTEx tissue expression → DepMap Chronos essentiality → ChEMBL tractability → full druggability SHAP scorecard.

### Phase 3 — Modality Routing
Rule engine scores each target across SM / AB / PROTAC / peptide / oligo. LLM gate confirms primary/secondary modality. Routes each target to P4 (repurpose), P5 (de novo SM), or P6 (de novo biologic) branches.

### Phase 4 — Drug Repurposing
- **Tier 1:** ChEMBL known-mechanism drugs (exhaustiveness=8, ~5–100 compounds)
- **Tier 2:** Full approved library screen (max 3000 compounds, exhaustiveness=4)
- **PrimeKG:** Knowledge graph drug-protein edge signal
- **LINCS:** Transcriptomic signature reversal score
- Triangulation score: 0.40×docking + 0.35×clinical + 0.25×KG
- LLM 4-sentence repurposing narrative for top candidates

### Phase 5 — De Novo Small Molecule
Seeds from: user-supplied SMILES + ChEMBL binders + **Phase 4 repurposing hits** (automatic).  
Generation: REINVENT4 Mol2Mol (if installed) → BRICS fragmentation/recombination fallback → built-in diverse scaffold library (always available).  
Filters: Ro5, Veber, PAINS, SA score, QED, Tanimoto novelty.  
ADMET: local RDKit hERG/AMES/BBB/hepatotoxicity/logS.  
Docking: Vina re-dock against Phase 2 pocket.

### Phase 6 — De Novo Biologic / Peptide
**6.1** Interface context extraction (hotspots, target class, design strategy).  
**6.2** Generation ladder:
1. RFdiffusion (local, `~/tools/RFdiffusion`) → ProteinMPNN sequence design
2. RFdiffusion direct path → ProteinMPNN
3. ProteinMPNN directly on target PDB (length-filtered to binder range)
4. LLM-assisted generation (always available)

**6.3** Developability: aggregation (hydrophobic window scan), solubility (charge balance), immunogenicity (NetMHCpan 4.2 MHC-I if installed, else heuristic), stability (N-end rule).  
**6.4** Boltz-1 CPU complex refolding for ipTM scoring (optional, ~45-90 min/complex).

### Phase 7 — Multi-Parameter Optimization
Active-learning MPO loop (up to 5 iterations): GP surrogate per objective, UCB acquisition, BRICS proposal for SM / single-residue mutation for biologics. Pareto front + 2D hypervolume convergence gate.

### Phase 8 — Validation Gate
Triple Vina re-dock (exhaustiveness=12) as pose stability check. 6-axis final scorecard: binding (0.30) + stability (0.20) + ADMET (0.20) + selectivity (0.15) + novelty (0.10) + modality alignment (0.05).

### Phase 9 — Packaging
Assembles reproducibility bundle: `README.md`, `candidates.csv`, `citations.bib`, version pins, LLM decision log. Zipped and uploaded to Supabase Storage.

---

## Local Tool Detection

The pipeline auto-detects tools at standard paths. Override with environment variables:

| Tool | Auto-detected path | Override env var |
|---|---|---|
| AutoDock Vina binary | `~/.local/bin/vina` | `VINA_BIN` |
| RFdiffusion | `~/tools/RFdiffusion/` | `RFDIFFUSION_DIR` |
| RFdiffusion Python | `~/miniforge3/envs/rfdiffusion/bin/python` | `RFDIFFUSION_PYTHON` |
| NetMHCpan 4.2 | `~/netMHCpan-4.2/netMHCpan` | — (add to PATH) |
| Boltz | `.venv/bin/boltz` | `BOLTZ_BIN` |
| REINVENT4 | system PATH (`reinvent` or `reinvent4`) | — |

---

## Configuration

All settings are in `src/config/settings.py` and `src/config/run_config.py`.

Key `RunConfig` fields:

```python
RunConfig(
    disease_name="Pancreatic Cancer",
    disease_efo_id="EFO_0002618",
    intent_mode="explore",          # explore | repurpose | de_novo
    known_positives=["KRAS", "TP53"],
    seed_smiles=["CC(=O)Nc1ccc(O)cc1"],  # optional — seeds P5 de novo generation
    indication_type="oncology",     # chronic | acute | oncology
    tissue_of_interest="Pancreas",
    candidates_per_target_max=10,
    llm=LLMConfig(provider="lmstudio"),  # lmstudio | anthropic | openai
)
```

### LLM Providers

```python
# LM Studio (default — local, free, no API key)
LLMConfig(provider="lmstudio", lmstudio=LLMLMStudioConfig(
    base_url="http://localhost:1234/v1",
    model="qwen/qwen3-4b-thinking-2507",
))

# Anthropic Claude
LLMConfig(provider="anthropic", anthropic=LLMAnthropicConfig(
    api_key_ref="sk-ant-...",
    model="claude-sonnet-4-6",
))

# OpenAI
LLMConfig(provider="openai", openai=LLMOpenAIConfig(
    api_key_ref="sk-...",
    model="gpt-4o",
))
```

---

## API Reference

The FastAPI backend exposes a REST API used by the React frontend. Run it and visit `/docs` for the full Swagger UI.

```
POST   /api/runs               Create and start a pipeline run
GET    /api/runs               List all runs
GET    /api/runs/{id}          Get run detail + phase outputs
DELETE /api/runs/{id}          Delete a run
GET    /api/runs/{id}/targets  Get ranked targets for a run
GET    /api/runs/{id}/candidates  Get drug candidates for a run
GET    /api/runs/{id}/stream   SSE stream of live phase events
GET    /api/genes?q=KRAS       Gene symbol autocomplete
GET    /api/system/telemetry   CPU/RAM/GPU usage
```

---

## Environment Variables

Create a `.env` file at the project root:

```env
# Supabase (required)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...

# Redis (optional — enables Celery parallel execution)
REDIS_URL=redis://localhost:6379/0

# LLM providers (optional — LM Studio is default)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Tool paths (optional — auto-detected at standard paths)
RFDIFFUSION_DIR=/path/to/RFdiffusion
RFDIFFUSION_PYTHON=/path/to/conda/envs/rfdiffusion/bin/python
BOLTZ_BIN=/path/to/boltz

# Pipeline caps
P4_MAX_LIBRARY=3000        # max compounds in repurposing library screen
P4_WORKERS=4               # parallel Vina workers
P5_N_GENERATE=1000         # molecules to generate per target
P5_TOP_N=20                # top candidates to keep
P6_N_GENERATE=30           # peptide sequences to generate
```

---

## Development

```bash
# Run tests
pytest testing/ -v

# Lint
ruff check src/

# Type check frontend
cd frontend && npx tsc --noEmit

# Run a single phase manually (useful for debugging)
python -c "
from src.config.run_config import RunConfig
from src.db.supabase_client import get_service_client
from src.phases.phase1.runner import run_phase1

config = RunConfig(
    disease_name='Pancreatic Cancer',
    disease_efo_id='EFO_0002618',
    known_positives=['KRAS', 'TP53', 'SMAD4'],
)
db = get_service_client()
# ... (create run first via bootstrap.create_run)
"
```

---

## Scientific Methodology

### Phase 1 — PU Learning
The target identification model treats known disease genes (user-supplied) as positive examples and the rest of the proteome as unlabelled. A bagging-PU ensemble of XGBoost classifiers estimates the probability that each gene is a disease-relevant drug target.

14 features per gene:
- Genetic: GWAS p-value, OMIM disease gene, DISEASES NLP score
- Expression: GTEx tissue specificity, HPA subcellular localisation
- Essentiality: DepMap Chronos CRISPR score
- Network: STRING PPI degree, betweenness centrality
- Pathway: PROGENy pathway activity, Reactome pathway membership
- Regulatory: DoRothEA TF regulon target
- Structural: AlphaFold pLDDT, number of druggable pockets (fpocket)
- Literature: SciHub co-citation score

### Phase 4 — Drug Repurposing
Follows the Pushpakom et al. 2019 NRD framework: three orthogonal signals (molecular docking, clinical evidence, knowledge graph) are triangulated. Vina scores are calibrated against a per-target ceiling derived from known binders.

### Phase 6 — Biologic Design
Peptide candidates are designed in a three-tier ladder: structure-based (RFdiffusion backbone → ProteinMPNN sequence design), followed by LLM-assisted generation when structural tools are unavailable. Developability is assessed against TANGO-proxy aggregation, NetSolP-proxy solubility, NetMHCpan 4.2 MHC-I immunogenicity, and N-end rule stability.

---

## Troubleshooting

**Phase 0 exits with `no_go`**  
Check the `missing_required` list in the Phase 0 output. Usually a missing database file or failed Supabase connection.

**RFdiffusion not being used in Phase 6**  
The logs will say `[6.rfdiff] RFdiffusion not found`. Set `RFDIFFUSION_DIR` to your clone or install to `~/tools/RFdiffusion`. Also ensure model weights are downloaded (`bash scripts/download_models.sh`).

**NetMHCpan fallback to heuristic**  
Check that `~/netMHCpan-4.2/netMHCpan` exists and is executable (`chmod +x`). The pipeline logs `NetMHCpan found: /path/...` at Phase 6 startup when detected.

**Vina docking producing no scores**  
Ensure the Vina binary is at `~/.local/bin/vina` (or set `VINA_BIN`). Check that `meeko` is installed: `pip install meeko`. Phase 2 must have produced pocket coordinates for docking to run.

**BRICS generates zero molecules**  
This happens when seed SMILES contain no BRICS-breakable bonds (e.g. only bare aromatic rings). The pipeline falls back to a built-in 12-scaffold library automatically. To get better results, provide user seed SMILES in the New Experiment form.

**Supabase connection refused**  
Make sure `.env` has correct `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`. For local Supabase, ensure the Docker container is running (`npx supabase status`).

---

## Project Status

This is a research prototype. The pipeline has been validated end-to-end on:
- KRAS G12C (pancreatic/lung cancer) — sotorasib recapitulation test
- TP53 (multiple cancers)

Phases 0–9 are implemented and smoke-tested. Production hardening, additional assay integrations (FEP, MD), and a collaborative multi-user workspace are on the roadmap.

---

## Citation

If you use RxDis in your research, please cite:

```bibtex
@software{rxdis2026,
  author = {Vyas, Rohan},
  title  = {RxDis: An AI-Native End-to-End Drug Discovery Pipeline},
  year   = {2026},
  url    = {https://github.com/RohanV01/AI-BioScientist},
}
```

---

## Acknowledgements

- [Open Targets](https://www.opentargets.org/) — disease-gene associations
- [ChEMBL](https://www.ebi.ac.uk/chembl/) — bioactivity database
- [PrimeKG](https://github.com/mims-harvard/PrimeKG) — precision medicine knowledge graph
- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina) — molecular docking
- [ProteinMPNN](https://github.com/dauparas/ProteinMPNN) — protein sequence design
- [RFdiffusion](https://github.com/RosettaCommons/RFdiffusion) — protein backbone diffusion
- [Boltz-1](https://github.com/jwohlwend/boltz) — structure prediction
- [NetMHCpan](https://services.healthtech.dtu.dk/services/NetMHCpan-4.2/) — MHC binding prediction
- [REINVENT4](https://github.com/MolecularAI/REINVENT4) — de novo molecule generation
- [DepMap](https://depmap.org/) — CRISPR essentiality data
- [GTEx](https://gtexportal.org/) — tissue expression data

---

## License

MIT License. See [LICENSE](LICENSE) for details.

Scientific databases included by reference only — download directly from their respective sources under their own licences (ChEMBL: CC BY-SA 3.0; PrimeKG: MIT; GTEx: dbGaP; OMIM: academic use).
