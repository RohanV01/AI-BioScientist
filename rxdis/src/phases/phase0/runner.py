"""
Phase 0 runner — validates everything before any real compute.
Returns the Phase 0 I/O contract JSON.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List

from src.config.run_config import RunConfig
from src.llm.factory import make_provider
from src.llm.provider import LLMProvider
from .checks import (
    check_all_databases,
    probe_supabase, probe_redis,
    probe_lmstudio, probe_anthropic, probe_openai,
    probe_ncbi, probe_omim, probe_open_targets,
    probe_gpu,
)

log = logging.getLogger(__name__)

# Rough cost estimate per phase from the compute budget table (USD, median run)
_PHASE_COST_USD = {
    1: 0.5,   # PubMed + API calls
    2: 8.0,   # structure prediction (NIM/AF)
    3: 0.5,   # modality selection (local)
    4: 5.0,   # virtual screening (NIM/Vina)
    5: 12.0,  # de novo SM (GenMol NIM + REINVENT)
    6: 8.0,   # de novo biologic (BoltzGen)
    7: 1.0,   # MPO scoring
    8: 3.0,   # MD / final validation
    9: 0.5,   # packaging
}


def run_phase0(run_id: str, config: RunConfig, db=None) -> Dict[str, Any]:
    """
    Execute Phase 0 checks.
    Returns the standardised output JSON (also written to phase_results by the task wrapper).
    """
    from src.db import run_state

    if db:
        run_state.mark_phase_running(db, run_id, phase=0)

    log.info("[Phase 0] Starting health checks for run %s", run_id)
    try:
        return _run_phase0_body(run_id, config, db, run_state)
    except Exception as exc:
        log.exception("[Phase 0] Failed for run %s", run_id)
        if db:
            try:
                run_state.mark_phase_failed(db, run_id, phase=0, error=f"{type(exc).__name__}: {exc}")
            except Exception:
                pass
        raise


def _run_phase0_body(run_id: str, config: RunConfig, db, run_state) -> Dict[str, Any]:

    # ── 0.1 Validate RunConfig ───────────────────────────────────────────────
    # Already validated by Pydantic at this point.

    # ── 0.2 Credential probes ────────────────────────────────────────────────
    credentials: List[Dict] = []

    # Supabase
    if db:
        credentials.append(probe_supabase())
    else:
        credentials.append({"service": "Supabase", "ok": False, "latency_ms": 0,
                            "detail": "No DB client provided (dry_run without DB)"})

    # Redis
    credentials.append(probe_redis())

    # LLM provider
    provider_cfg = config.llm
    if provider_cfg.provider == "lmstudio":
        cred = probe_lmstudio(
            provider_cfg.lmstudio.base_url,
            provider_cfg.lmstudio.model,
        )
    elif provider_cfg.provider == "anthropic":
        from src.config import settings
        key = settings.ANTHROPIC_API_KEY
        cred = probe_anthropic(key, provider_cfg.anthropic.model)
    else:
        from src.config import settings
        key = settings.OPENAI_API_KEY
        cred = probe_openai(key, provider_cfg.openai.model)
    credentials.append(cred)

    # Optional / phase-gated APIs
    from src.config import settings
    if settings.NCBI_API_KEY:
        credentials.append(probe_ncbi(settings.NCBI_API_KEY))
    if settings.OMIM_API_KEY:
        credentials.append(probe_omim(settings.OMIM_API_KEY))

    credentials.append(probe_open_targets())

    # ── 0.3 Database presence ────────────────────────────────────────────────
    databases = check_all_databases()

    # ── 0.4 Hosted endpoint health (deprecation guard) ───────────────────────
    endpoints = _probe_hosted_endpoints(settings.NIM_API_KEY)

    # ── 0.5 Cost estimate ────────────────────────────────────────────────────
    phases_active = [p for p in config.phases_to_run() if p > 0]
    cost_estimate = sum(_PHASE_COST_USD.get(p, 0) for p in phases_active)
    cost_estimate *= max(1, config.target_count_max // 5)  # scale with target count

    # ── 0.6 GPU probe ────────────────────────────────────────────────────────
    gpu_info = probe_gpu()

    # ── Determine go/no-go ───────────────────────────────────────────────────
    missing_required: List[str] = []

    llm_ok = any(c["service"] in ("LMStudio", "Anthropic", "OpenAI") and c["ok"]
                 for c in credentials)
    if not llm_ok:
        missing_required.append("LLM provider (LMStudio/Anthropic/OpenAI)")

    redis_ok = next((c["ok"] for c in credentials if c["service"] == "Redis"), False)
    if not redis_ok:
        missing_required.append("Redis")

    required_dbs = ["PrimeKG", "STRING", "BioGRID", "GTEx", "AlphaMissense", "ChEMBL"]
    for db_check in databases:
        if db_check["name"] in required_dbs and not db_check["present"]:
            missing_required.append(f"Database:{db_check['name']}")

    go_no_go = "go" if not missing_required else "no_go"

    # ── LLM summary ─────────────────────────────────────────────────────────
    if llm_ok and not config.dry_run:
        try:
            provider = make_provider(config.llm)
            summary_prompt = _build_summary_prompt(credentials, databases, missing_required,
                                                   cost_estimate, go_no_go)
            summary_result = provider.complete(summary_prompt, temperature=0.1, max_tokens=512)
            summary_text = summary_result.text
        except Exception as exc:
            summary_text = f"(LLM summary unavailable: {exc})"
    else:
        summary_text = _static_summary(go_no_go, missing_required)

    output = {
        "credentials": credentials,
        "databases": databases,
        "endpoints": endpoints,
        "gpu": gpu_info,
        "cost_estimate_usd": round(cost_estimate, 2),
        "missing_required": missing_required,
        "go_no_go": go_no_go,
        "summary": summary_text,
    }

    if db:
        if go_no_go == "go":
            run_state.mark_phase_completed(db, run_id, phase=0, output=output)
        else:
            run_state.mark_phase_failed(db, run_id, phase=0,
                                         error=f"Missing: {missing_required}")

    log.info("[Phase 0] go_no_go=%s  cost_estimate=$%.2f", go_no_go, cost_estimate)
    return output


def _probe_hosted_endpoints(nim_key: str) -> List[Dict]:
    """Check NIM model endpoints for availability / deprecation."""
    nim_models = [
        "alphafold2-nim",
        "diffdock",
        "rfdiffusion",
        "proteinmpnn",
        "genmol",
    ]
    results = []
    if not nim_key:
        return [{"model": m, "live": None, "deprecated": None, "detail": "no NIM key"} for m in nim_models]

    import httpx
    for model in nim_models:
        try:
            resp = httpx.get(
                f"https://api.nvcf.nvidia.com/v2/nvcf/functions/{model}",
                headers={"Authorization": f"Bearer {nim_key}"},
                timeout=8,
            )
            if resp.status_code == 404:
                results.append({"model": model, "live": False, "deprecated": True, "detail": "404 not found"})
            else:
                results.append({"model": model, "live": True, "deprecated": False, "detail": "ok"})
        except Exception as exc:
            results.append({"model": model, "live": False, "deprecated": None, "detail": str(exc)})

    return results


def _build_summary_prompt(creds, dbs, missing, cost, verdict) -> str:
    failing_creds = [c["service"] for c in creds if not c["ok"]]
    missing_dbs = [d["name"] for d in dbs if not d["present"]]
    return (
        f"You are a bioinformatics pipeline assistant. Summarize the following health-check results "
        f"in 2-3 plain English sentences for the user.\n\n"
        f"Verdict: {verdict}\n"
        f"Cost estimate: ${cost:.2f}\n"
        f"Failing credentials: {failing_creds or 'none'}\n"
        f"Missing databases: {missing_dbs or 'none'}\n"
        f"Missing required: {missing or 'none'}\n\n"
        f"Give a go/fix_first/no_go recommendation and name exactly what needs fixing if anything."
    )


def _static_summary(verdict: str, missing: List[str]) -> str:
    if verdict == "go":
        return "All credentials and databases validated. Pipeline is ready to run."
    items = ", ".join(missing)
    return f"Pipeline cannot proceed. Missing required: {items}. Fix these before starting a run."
