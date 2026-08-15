"""
Run bootstrap — create the DB records a run needs before the pipeline starts.

The CLI (`scripts/kickoff.py`) historically created a throwaway auth user +
profile + project for every run. For the React studio we instead reuse a single
persistent "Local Studio" user/project so the Runs list stays coherent across
restarts. The owner/project ids are resolved once and cached in-process.
"""
from __future__ import annotations
import logging
from typing import Optional, Tuple  # noqa: F401

from src.config import settings
from src.config.run_config import RunConfig

log = logging.getLogger(__name__)

_LOCAL_EMAIL = "studio@local.studio"
_LOCAL_ORG = "Local Studio"
_LOCAL_PROJECT = "Local Studio"

# (owner_id, project_id) cached after first resolution.
_local_ids: Optional[Tuple[str, str]] = None


def get_or_create_local_project(db) -> Tuple[str, str]:
    """
    Resolve (owner_id, project_id) for the persistent local-studio account,
    creating the auth user / profile / project on first use. Cached in-process.
    """
    global _local_ids
    if _local_ids is not None:
        return _local_ids

    owner_id = _find_or_create_owner(db)
    project_id = _find_or_create_project(db, owner_id)
    _local_ids = (owner_id, project_id)
    log.info("[bootstrap] local studio owner=%s project=%s", owner_id, project_id)
    return _local_ids


def _find_or_create_owner(db) -> str:
    # Profiles is the source of truth we can query with the table API.
    try:
        resp = db.table("profiles").select("id").eq("email", _LOCAL_EMAIL).limit(1).execute()
        if resp.data:
            return resp.data[0]["id"]
    except Exception as exc:
        log.warning("[bootstrap] profile lookup failed: %s", exc)

    # Try to find existing auth user before creating.
    try:
        users_resp = db.auth.admin.list_users()
        for u in (users_resp or []):
            if getattr(u, "email", None) == _LOCAL_EMAIL:
                owner_id = u.id
                db.table("profiles").upsert(
                    {"id": owner_id, "email": _LOCAL_EMAIL, "org": _LOCAL_ORG},
                    on_conflict="id",
                ).execute()
                log.info("[bootstrap] recovered existing local studio auth user %s", owner_id)
                return owner_id
    except Exception as exc:
        log.warning("[bootstrap] admin list_users failed: %s", exc)

    # Create the auth user (service role) then the profile row.
    user_resp = db.auth.admin.create_user({
        "email": _LOCAL_EMAIL,
        "password": settings.LOCAL_STUDIO_PASSWORD,
        "email_confirm": True,
    })
    owner_id = user_resp.user.id
    db.table("profiles").upsert(
        {"id": owner_id, "email": _LOCAL_EMAIL, "org": _LOCAL_ORG},
        on_conflict="id",
    ).execute()
    log.info("[bootstrap] created local studio auth user %s", owner_id)
    return owner_id


def _find_or_create_project(db, owner_id: str) -> str:
    try:
        resp = (
            db.table("projects")
            .select("id")
            .eq("owner_id", owner_id)
            .eq("name", _LOCAL_PROJECT)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]["id"]
    except Exception as exc:
        log.warning("[bootstrap] project lookup failed: %s", exc)

    proj = db.table("projects").insert(
        {"owner_id": owner_id, "name": _LOCAL_PROJECT}
    ).execute()
    return proj.data[0]["id"]


def get_or_create_project_for_user(db, owner_id: str) -> str:
    """Get or create a default project for an authenticated user."""
    try:
        resp = (
            db.table("projects")
            .select("id")
            .eq("owner_id", owner_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]["id"]
    except Exception as exc:
        log.warning("[bootstrap] project lookup failed for user %s: %s", owner_id, exc)

    proj = db.table("projects").insert(
        {"owner_id": owner_id, "name": "My Project"}
    ).execute()
    return proj.data[0]["id"]


def create_module_run(db, phase_num: int, run_name: str, owner_id: Optional[str] = None) -> str:
    """Insert a minimal runs row for a single-phase module run."""
    if owner_id:
        project_id = get_or_create_project_for_user(db, owner_id)
    else:
        owner_id, project_id = get_or_create_local_project(db)

    label = run_name.strip() or f"module_p{phase_num}"
    run = db.table("runs").insert({
        "project_id": project_id,
        "owner_id": owner_id,
        "disease_name": label,
        "config": {"phase": phase_num, "module_run": True},
        "intent_mode": "explore",
        "dry_run": False,
        "status": "pending",
    }).execute()
    run_id = run.data[0]["id"]
    log.info("[bootstrap] created module run %s owner=%s phase=%d", run_id, owner_id, phase_num)
    return run_id


def create_run(db, config: RunConfig, owner_id: Optional[str] = None) -> str:
    """Insert a runs row for this config and return its id.

    If owner_id is provided (authenticated user), the run is created under that
    user's project. Otherwise falls back to the persistent Local Studio account.
    """
    if owner_id:
        project_id = get_or_create_project_for_user(db, owner_id)
    else:
        owner_id, project_id = get_or_create_local_project(db)

    row: dict = {
        "project_id": project_id,
        "owner_id": owner_id,
        "disease_name": config.disease_name,
        "config": config.model_dump(mode="json"),
        "intent_mode": config.intent_mode,
        "dry_run": bool(config.dry_run),
        "status": "pending",
    }
    if config.disease_efo_id:
        row["efo_id"] = config.disease_efo_id
    run = db.table("runs").insert(row).execute()
    run_id = run.data[0]["id"]
    log.info("[bootstrap] created run %s owner=%s '%s'", run_id, owner_id, config.disease_name)
    return run_id
