"""Threads the current Experiment's own folder into in-process MCP tool calls
(app/tools/literature_discovery.py's download_paper/read_paper) without
touching every builder signature in app/tool_roster.py -- build_tool_roster()
builds every tool eagerly and zero-arg once per agent run, so there's no
per-call parameter-passing hook to use instead. Since SDK MCP tools run
in-process, in the same asyncio task tree as the code that calls
claude_runner.run_agent (confirmed by calling a tool's .handler() directly as
a plain coroutine), a contextvar set right before that call is visible inside
the tool without any roster changes.

Unset (the default) falls back to the old global settings.papers_download_dir
behavior -- standalone/test invocations of these tools outside a live agent
run keep working unchanged.
"""
import contextvars
import json
from pathlib import Path

current_experiment_dir: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "current_experiment_dir", default=None
)


def papers_dir() -> Path | None:
    exp_dir = current_experiment_dir.get()
    return (exp_dir / "papers") if exp_dir is not None else None


def findings_dir() -> Path | None:
    exp_dir = current_experiment_dir.get()
    return (exp_dir / "findings") if exp_dir is not None else None


def uploads_dir() -> Path | None:
    """Where real researcher-uploaded files for the current experiment
    live (a Mattermost message's file attachments, downloaded by
    app/routers/mattermost_webhook.py before the agent run starts --
    see app/file_uploads.py). Same contextvar-based pattern as
    papers_dir()/findings_dir() above."""
    exp_dir = current_experiment_dir.get()
    return (exp_dir / "uploads") if exp_dir is not None else None


def _manifest_path() -> Path | None:
    exp_dir = current_experiment_dir.get()
    return (exp_dir / "papers.json") if exp_dir is not None else None


def load_manifest() -> dict[str, dict]:
    """DOI -> {title, status: discovered|downloaded|read|skipped, ...} for the
    current experiment. Empty dict if no experiment is in scope or nothing's
    been recorded yet -- see the Experiments plan's paper-selection gate.
    """
    path = _manifest_path()
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text())


def save_manifest(manifest: dict[str, dict]) -> None:
    path = _manifest_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))


def update_manifest_entry(doi: str, **fields) -> None:
    """Merge `fields` into this DOI's manifest entry (creating it if new). A
    no-op if no experiment is in scope -- callers don't need to branch on
    whether one is."""
    if current_experiment_dir.get() is None:
        return
    manifest = load_manifest()
    entry = manifest.setdefault(doi, {})
    entry.update(fields)
    save_manifest(manifest)
