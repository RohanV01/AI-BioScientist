"""
FastAPI bridge between the React studio and the Python pipeline.

Run:  .venv/bin/uvicorn src.api.main:app --reload --port 8000
The React dev server (Vite, :5173) proxies /api and the WebSocket to here.

Endpoints
  POST /api/runs                     create + start a run (background thread)
  GET  /api/runs                     list runs (newest first)
  GET  /api/runs/{id}                run header + phase_results
  GET  /api/runs/{id}/targets        ranked/validated targets
  GET  /api/runs/{id}/decisions      LLM gate audit trail
  GET  /api/runs/{id}/compute        compute/cost log
  GET  /api/runs/{id}/candidates     candidates from phases 4–8
  GET  /api/runs/{id}/events         replay buffer (polling fallback)
  WS   /api/runs/{id}/stream         live event stream (replay then tail)
  GET  /api/system/telemetry         RAM / VRAM / CPU snapshot
  GET  /api/genes?q=                 gene-symbol search for the PU anchor
  GET  /api/health                   liveness + Supabase reachability
"""
from __future__ import annotations

import asyncio
import logging
import structlog
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api import events as ev
from src.api.orchestrator import PHASE_NAMES, MAX_IMPLEMENTED_PHASE, is_running, start_run
from src.config import settings
from src.config.run_config import RunConfig
from src.db import bootstrap
from src.db.run_state import get_phase_output, mark_phase_failed
from src.db.supabase_client import get_service_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
log = logging.getLogger("api")

app = FastAPI(title="In-Silico Drug Discovery Studio", version="1.0")


@app.on_event("startup")
async def _mark_orphaned_runs_failed() -> None:
    """Any run still 'pending' or 'running' at startup has no live thread — mark it failed."""
    try:
        db = get_service_client()
        db.table("runs").update({"status": "failed"}).in_(
            "status", ["pending", "running"]
        ).execute()
        log.info("[startup] orphaned pending/running runs marked failed")
    except Exception as exc:
        log.warning("[startup] could not mark orphaned runs: %s", exc)

_limiter = Limiter(key_func=get_remote_address)
app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"] + [
    o.strip() for o in getattr(settings, "EXTRA_CORS_ORIGINS", "").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str | None:
    if creds is None:
        return None
    token = creds.credentials
    try:
        resp = get_service_client().auth.get_user(token)
        return resp.user.id if resp.user else None
    except Exception as exc:
        log.warning("JWT verification failed: %s", exc)
        raise HTTPException(401, "Invalid or expired token")


# ── Request models ───────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    disease: str
    disease_efo_id: Optional[str] = None
    intent_mode: str = "explore"                 # explore | repurpose | de_novo
    known_positives: List[str] = Field(default_factory=list)
    seed_smiles: List[str] = Field(default_factory=list)
    exclude_targets: List[str] = Field(default_factory=list)
    tissue_of_interest: str = "Lung"
    indication_type: str = "oncology"            # chronic | acute | oncology
    provider: str = "lmstudio"                   # lmstudio | anthropic | openai
    target_count_max: int = 20
    pu_n_bags: int = 30
    through_phase: int = 1                        # 0..MAX_IMPLEMENTED_PHASE

    @field_validator("disease")
    @classmethod
    def disease_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("disease is required")
        return v.strip()


class ArtifactInput(BaseModel):
    source: Literal["upload", "run", "manual"] = "manual"
    source_run_id: Optional[str] = None
    source_phase: Optional[int] = None
    data: Optional[Dict[str, Any]] = None

    @field_validator("data")
    @classmethod
    def validate_data_size(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return v
        import json
        raw = json.dumps(v)
        if len(raw) > 10 * 1024 * 1024:  # 10 MB limit
            raise ValueError("Artifact data exceeds 10 MB limit")
        return v

    @field_validator("source_run_id")
    @classmethod
    def validate_run_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        if not re.match(r'^[0-9a-f-]{36}$', v):
            raise ValueError("source_run_id must be a valid UUID")
        return v


# ── Supabase read helpers (service role; local single-user) ──────────────────

def _db():
    return get_service_client()


def _list_runs() -> List[Dict[str, Any]]:
    try:
        resp = (_db().table("runs")
                .select("id,disease_name,status,current_phase,intent_mode,efo_id,cost_estimate,created_at")
                .order("created_at", desc=True).limit(100).execute())
        return resp.data or []
    except Exception as exc:
        log.warning("list_runs failed: %s", exc)
        return []


def _get_run(run_id: str) -> Optional[Dict[str, Any]]:
    try:
        run = _db().table("runs").select("*").eq("id", run_id).single().execute().data
    except Exception as exc:
        log.warning("get_run failed: %s", exc)
        return None
    phases = []
    try:
        phases = (_db().table("phase_results")
                  .select("phase,status,started_at,finished_at,error")
                  .eq("run_id", run_id).order("phase").execute().data or [])
    except Exception:
        pass
    return {"run": run, "phases": phases, "running": is_running(run_id)}


def _get_targets(run_id: str) -> List[Dict[str, Any]]:
    try:
        resp = (_db().table("targets")
                .select("rank,symbol,ensembl_id,aggregate_score,validation_score,tdl,"
                        "modality_primary,modality_secondary,evidence_trail")
                .eq("run_id", run_id).order("rank").execute())
        return resp.data or []
    except Exception as exc:
        log.warning("get_targets failed: %s", exc)
        return []


def _get_candidates(run_id: str) -> List[Dict[str, Any]]:
    try:
        resp = (
            _db().table("candidates")
            .select("id,target_id,kind,identifier,smiles,sequence,combined_score,subscores,created_at")
            .eq("run_id", run_id)
            .order("combined_score", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        log.warning("get_candidates failed: %s", exc)
        return []


def _get_decisions(run_id: str) -> List[Dict[str, Any]]:
    try:
        resp = (_db().table("decisions")
                .select("phase,gate,llm_provider,llm_model,decision_json,created_at")
                .eq("run_id", run_id).order("created_at").execute())
        return resp.data or []
    except Exception:
        return []


def _get_compute(run_id: str) -> List[Dict[str, Any]]:
    try:
        resp = (_db().table("compute_log")
                .select("phase,step,service,cost_usd,wall_time_s,created_at")
                .eq("run_id", run_id).order("created_at").execute())
        return resp.data or []
    except Exception:
        return []


# ── Gene universe (cached) for the PU-anchor search ──────────────────────────

_gene_universe: Optional[List[str]] = None


def _genes() -> List[str]:
    global _gene_universe
    if _gene_universe is None:
        try:
            from src.phases.phase1.matrix import _load_gene_universe
            _gene_universe = sorted({g for g in _load_gene_universe() if g})
        except Exception as exc:
            log.warning("gene universe load failed: %s", exc)
            _gene_universe = []
    return _gene_universe


def _search_genes(q: str, limit: int) -> List[str]:
    q = (q or "").strip().upper()
    if not q:
        return []
    genes = _genes()
    pref = [g for g in genes if g.upper().startswith(q)]
    if len(pref) >= limit:
        return pref[:limit]
    sub = [g for g in genes if q in g.upper() and not g.upper().startswith(q)]
    return (pref + sub)[:limit]


# ── REST routes ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> Dict[str, Any]:
    ok = True
    detail = "ok"
    try:
        await run_in_threadpool(lambda: _db().table("runs").select("id").limit(1).execute())
    except Exception as exc:
        ok = False
        detail = str(exc)
    return {"status": "ok", "supabase": ok, "detail": detail,
            "phases_implemented": list(range(0, MAX_IMPLEMENTED_PHASE + 1))}


@app.get("/api/system/telemetry")
async def telemetry() -> Dict[str, Any]:
    return await run_in_threadpool(ev.read_telemetry)


@app.get("/api/genes")
@_limiter.limit("60/minute")
async def genes(request: Request, q: str = Query(""), limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
    results = await run_in_threadpool(_search_genes, q, limit)
    return {"query": q, "results": results}


@app.get("/api/runs")
async def list_runs() -> Dict[str, Any]:
    runs = await run_in_threadpool(_list_runs)
    for r in runs:
        r["running"] = is_running(r["id"])
    return {"runs": runs, "phase_names": PHASE_NAMES}


@app.post("/api/runs")
@_limiter.limit("5/minute")
async def create_run(request: Request, req: RunRequest, user_id: str | None = Depends(get_current_user_id)) -> Dict[str, Any]:
    import re as _re
    _sanitized_disease = _re.sub(r'[^\w\s\-\(\)]', '', req.disease.strip())[:200]
    if not _sanitized_disease.strip():
        raise HTTPException(422, "disease contains no valid characters")

    positives = [p.strip() for p in req.known_positives if p.strip()]
    if not positives:
        raise HTTPException(400, "At least one known positive gene is required to anchor PU learning.")

    try:
        cfg = RunConfig(
            disease_name=_sanitized_disease,
            disease_efo_id=req.disease_efo_id or None,
            intent_mode=req.intent_mode,            # type: ignore[arg-type]
            indication_type=req.indication_type,    # type: ignore[arg-type]
            tissue_of_interest=req.tissue_of_interest or "Lung",
            known_positives=positives,
            seed_targets=positives,
            seed_smiles=[s.strip() for s in req.seed_smiles if s.strip()],
            exclude_targets=[e.strip() for e in req.exclude_targets if e.strip()],
            target_count_max=int(req.target_count_max),
            pu_n_bags=int(req.pu_n_bags),
            llm={"provider": req.provider},         # type: ignore[arg-type]
        )
    except Exception as exc:
        raise HTTPException(422, f"Invalid run config: {exc}")

    try:
        run_id = await run_in_threadpool(bootstrap.create_run, _db(), cfg)
    except Exception as exc:
        raise HTTPException(502, f"Could not create run in Supabase: {exc}")

    hub = ev.registry.get_or_create(run_id)
    hub.bind_loop(asyncio.get_running_loop())
    start_run(run_id, cfg, hub, through_phase=req.through_phase)
    return {"run_id": run_id, "through_phase": min(max(req.through_phase, 0), MAX_IMPLEMENTED_PHASE)}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    data = await run_in_threadpool(_get_run, run_id)
    if not data or not data.get("run"):
        raise HTTPException(404, "run not found")
    return data


@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: str) -> Dict[str, Any]:
    run_data = await run_in_threadpool(_get_run, run_id)
    if not run_data or not run_data.get("run"):
        raise HTTPException(404, "run not found")
    if run_data["run"].get("status") == "running":
        raise HTTPException(409, "cannot delete a running run")

    def _delete(rid: str) -> None:
        db = _db()
        for tbl, col in [("phase_results", "run_id"), ("targets", "run_id"),
                         ("candidates", "run_id"), ("decisions", "run_id")]:
            try:
                db.table(tbl).delete().eq(col, rid).execute()
            except Exception:
                pass
        db.table("runs").delete().eq("id", rid).execute()

    await run_in_threadpool(_delete, run_id)
    return {"deleted": run_id}


@app.get("/api/runs/{run_id}/targets")
async def get_targets(run_id: str) -> Dict[str, Any]:
    return {"targets": await run_in_threadpool(_get_targets, run_id)}


@app.get("/api/runs/{run_id}/candidates")
async def get_candidates(run_id: str) -> Dict[str, Any]:
    return {"candidates": await run_in_threadpool(_get_candidates, run_id)}


@app.get("/api/runs/{run_id}/decisions")
async def get_decisions(run_id: str) -> Dict[str, Any]:
    return {"decisions": await run_in_threadpool(_get_decisions, run_id)}


@app.get("/api/runs/{run_id}/compute")
async def get_compute(run_id: str) -> Dict[str, Any]:
    return {"compute": await run_in_threadpool(_get_compute, run_id)}


@app.get("/api/runs/{run_id}/events")
async def get_events(run_id: str) -> Dict[str, Any]:
    hub = ev.registry.get(run_id)
    if hub is None:
        return {"events": [], "running": False, "done": True}
    return {"events": hub.replay(), "running": is_running(run_id), "done": hub.done}


# ── WebSocket live stream ────────────────────────────────────────────────────

@app.websocket("/api/runs/{run_id}/stream")
async def stream(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    hub = ev.registry.get_or_create(run_id)
    hub.bind_loop(asyncio.get_running_loop())
    q = hub.subscribe()
    try:
        for evt in hub.replay():
            await ws.send_json(evt)
        await ws.send_json({"type": "synced", "running": is_running(run_id), "done": hub.done})
        while True:
            evt = await q.get()
            await ws.send_json(evt)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("ws closed for %s: %s", run_id, exc)
    finally:
        hub.unsubscribe(q)


@app.websocket("/api/module-runs/{run_id}/stream")
async def module_stream(ws: WebSocket, run_id: str) -> None:
    """Alias: module runs share the same WebSocket streaming logic as E2E runs."""
    await ws.accept()
    hub = ev.registry.get_or_create(run_id)
    hub.bind_loop(asyncio.get_running_loop())
    q = hub.subscribe()
    try:
        for evt in hub.replay():
            await ws.send_json(evt)
        await ws.send_json({"type": "synced", "running": is_running(run_id), "done": hub.done})
        while True:
            evt = await q.get()
            await ws.send_json(evt)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("ws closed for module run %s: %s", run_id, exc)
    finally:
        hub.unsubscribe(q)


# ── Static SPA (production build) ────────────────────────────────────────────

_DIST = Path(__file__).parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")
else:
    @app.get("/")
    async def root() -> JSONResponse:
        return JSONResponse({
            "studio": "In-Silico Drug Discovery",
            "ui": "Run the Vite dev server in ./frontend (npm run dev), or build it (npm run build) to serve here.",
            "docs": "/docs",
        })
