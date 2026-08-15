"""
Global settings loaded from .env and environment variables.
All phase code imports from here — never reads os.environ directly.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from repo root (two levels up from this file)
_ENV_FILE = Path(__file__).parents[2] / ".env"
load_dotenv(_ENV_FILE, override=False)


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Required env var {key!r} is missing. Add it to .env")
    return val


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ── Supabase ────────────────────────────────────────────────────────────────
SUPABASE_URL: str = _get("SUPABASE_URL")
SUPABASE_SERVICE_KEY: str = _get("SUPABASE_SERVICE_KEY")
SUPABASE_ANON_KEY: str = _get("SUPABASE_ANON_KEY")
LOCAL_STUDIO_PASSWORD: str = _get("LOCAL_STUDIO_PASSWORD", "local-studio-password")

# ── Redis / Celery ───────────────────────────────────────────────────────────
REDIS_URL: str = _get("REDIS_URL", "redis://localhost:6379/0")

# ── LLM providers ───────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = _get("ANTHROPIC_API_KEY")
OPENAI_API_KEY: str = _get("OPENAI_API_KEY")
LMSTUDIO_BASE_URL: str = _get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL: str = _get("LMSTUDIO_MODEL", "qwen/qwen3-4b-thinking-2507")

# ── External APIs ────────────────────────────────────────────────────────────
NIM_API_KEY: str = _get("NIM_API_KEY")
NEUROSNAP_API_KEY: str = _get("NEUROSNAP_API_KEY")
MODAL_TOKEN: str = _get("MODAL_TOKEN")
RUNPOD_API_KEY: str = _get("RUNPOD_API_KEY")
CLUE_API_KEY: str = _get("CLUE_API_KEY")
OMIM_API_KEY: str = _get("OMIM_API_KEY")
NCBI_API_KEY: str = _get("NCBI_API_KEY")
AFSERVER_COOKIE: str = _get("AFSERVER_COOKIE")
DISGENET_API_KEY: str = _get("DISGENET_API_KEY")

# ── GPU ──────────────────────────────────────────────────────────────────────
GPU_SHARING_MODE: str = _get("GPU_SHARING_MODE", "lmstudio_resident")

# ── Databases (local paths) ──────────────────────────────────────────────────
_DB_ROOT = Path(__file__).parents[2] / "Databases"

DB_PRIMEKG = _DB_ROOT / "primekg"
DB_DEPMAP = _DB_ROOT / "depmap"
DB_STRING = _DB_ROOT / "string"
DB_BIOGRID = _DB_ROOT / "biogrid"
DB_GTEX = _DB_ROOT / "gtex"
DB_ALPHAMISSENSE = _DB_ROOT / "alphamissense"
DB_CHEMBL = _DB_ROOT / "chembl"
DB_HPA = _DB_ROOT / "human_protein_atlas"
DB_GWAS = _DB_ROOT / "gwas_catalog"
DB_OMIM = _DB_ROOT / "omim"

# ── Concurrency & rate limits ────────────────────────────────────────────────
MAX_CONCURRENT_THREAD_RUNS: int = int(_get("MAX_CONCURRENT_THREAD_RUNS", "10"))
RATE_LIMIT_RUNS_PER_MINUTE: str = _get("RATE_LIMIT_RUNS_PER_MINUTE", "5/minute")
RATE_LIMIT_GLOBAL_PER_MINUTE: str = _get("RATE_LIMIT_GLOBAL_PER_MINUTE", "120/minute")
