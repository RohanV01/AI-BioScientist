# Installation Guide

Three install tiers, in order. **Do not skip the version warning.**

> ⚠️ **Python version:** This project requires **Python 3.10**. Your current
> `.venv` is Python 3.14, on which RDKit / OpenMM / GROMACS / pdbfixer cannot
> build today. Use the conda env below instead of the existing `.venv` for the
> scientific worker. (The web/API layer alone could run on 3.11+, but to keep
> one environment we standardize on 3.10.)

---

## Tier 1 — Conda scientific base (compiled tools)

```bash
# Install miniforge/mambaforge if you don't have conda
conda env create -f environment.yml      # creates 'rxdis' on Python 3.10
conda activate rxdis
```

This installs: RDKit, OpenBabel, OpenMM, GROMACS, pdbfixer, mdtraj, build tools.

---

## Tier 2 — Pip layer (web, orchestration, clients, ML)

```bash
# inside the activated rxdis env
pip install -r requirements.txt
playwright install chromium               # for PockDrug/SwissADME/SAbPred automation
```

---

## Tier 3 — Manual installs (NOT pip/conda)

These are git-clones or academic-server downloads. Each is optional depending on `intent_mode`.

| Tool | Needed for | Install |
|---|---|---|
| **fpocket** | Phase 2.3 pocket detection | `git clone https://github.com/Discngine/fpocket && cd fpocket && make && sudo make install` |
| **ProteinMPNN** | Phase 6.2 sequence design | `git clone https://github.com/dauparas/ProteinMPNN` (run via its own script) |
| **ADFRsuite** | Phase 4.3/5.1 receptor prep (`prepare_receptor4.py`) | Download from https://ccsb.scripps.edu/adfr/downloads/ |
| **NetMHCpan 4.1** | Phase 6.5 immunogenicity | Academic download: https://services.healthtech.dtu.dk/services/NetMHCpan-4.1 |
| **TANGO** | Phase 6.5 aggregation | http://tango.crg.es (CLI) |
| **IUPred3** | Phase 2.6 disorder | https://iupred3.elte.hu (CLI/script) |
| **BindCraft** | Phase 6.1 fallback only (≥32 GB GPU) | `git clone https://github.com/martinpacesa/BindCraft` — RunPod/A100 only |
| **boltz** (local) | Phase 4/5/8 (small batches) | `pip install boltz` (already in requirements; large model download on first run) |

---

## Tier 4 — Infrastructure services

```bash
# Redis (Celery broker)
docker run -d -p 6379:6379 redis:7        # or: sudo apt install redis-server

# LM Studio (local LLM) — GUI app
#   1. Install LM Studio
#   2. Download model: qwen/qwen3-4b-thinking-2507
#   3. Start Local Server (Developer tab) -> http://localhost:1234

# Supabase — create a project at https://supabase.com (or self-host)
#   Run the schema migration from MASTER_PRD.md §4 (Data Model)
```

---

## Tier 5 — Secrets

Copy `.env.example` → `.env` and fill in:

```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_ANON_KEY=
REDIS_URL=redis://localhost:6379/0

# ── LLM providers (pluggable, per-user) — see docs/PRD_llm_provider_layer.md ──
# Users supply their own keys in the UI per run; these env defaults are optional
# fallbacks for server-wide / dev use. At least one provider must be reachable.
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=qwen/qwen3-4b-thinking-2507
ANTHROPIC_API_KEY=          # optional default; users can supply their own per run
OPENAI_API_KEY=             # optional default; users can supply their own per run
LLM_ENC_KEY=                # symmetric key to encrypt saved user LLM credentials (pgcrypto)

# ── Hosted compute ──
NIM_API_KEY=
NEUROSNAP_API_KEY=
MODAL_TOKEN=
RUNPOD_API_KEY=
CLUE_API_KEY=
OMIM_API_KEY=
NCBI_API_KEY=
GPU_SHARING_MODE=lmstudio_resident      # or 'exclusive'
```

---

## Verify

```bash
conda activate rxdis
python -c "import rdkit, openmm, networkx, botorch, xgboost; print('sci OK')"
python -c "import fastapi, celery, supabase, openai, gradio; print('web OK')"
python -c "from openai import OpenAI; c=OpenAI(base_url='http://localhost:1234/v1', api_key='x'); print([m.id for m in c.models.list().data])"
redis-cli ping        # -> PONG
```

Then run a **dry run** from the UI (or API) to validate all credentials + estimate cost before committing real compute (Phase 0).
