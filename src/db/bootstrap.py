"""
Run bootstrap — create the DB records a run needs before the pipeline starts.

The CLI (`scripts/kickoff.py`) historically created a throwaway auth user +
profile + project for every run. For the React studio we instead reuse a single
persistent "Local Studio" user/project so the Runs list stays coherent across
restarts. The owner/project ids are resolved once and cached in-process.
"""
from __future__ import annotations
import logging
from typing import Optional, Tuple

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

    # Create the auth user (service role) then the profile row.
    user_resp = db.auth.admin.create_user({
        "email": _LOCAL_EMAIL,
        "password": "local-studio-pw-001",
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


def create_run(db, config: RunConfig) -> str:
    """Insert a `runs` row for this config and return its id (status='pending')."""
    owner_id, project_id = get_or_create_local_project(db)
    run = db.table("runs").insert({
        "project_id": project_id,
        "owner_id": owner_id,
        "disease_name": config.disease_name,
        "config": config.model_dump(mode="json"),
        "intent_mode": config.intent_mode,
        "dry_run": bool(config.dry_run),
        "status": "pending",
    }).execute()
    run_id = run.data[0]["id"]
    log.info("[bootstrap] created run %s for '%s'", run_id, config.disease_name)
    return run_id
