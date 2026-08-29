"""Auto-generated Methods section (docs/18-platform-capability-gaps.md
Pass 2 #5, the other highest-value/lowest-effort item alongside
retraction detection -- see that doc for why). Every computational
biology paper needs a "Methods" section naming exactly which software
and data sources produced its results; this platform already tracks
that precisely in `ToolCall`/`GroundingLink`, it just wasn't rendered
anywhere. Pure DB query + template render -- no external network call,
no new architecture, same shape as `app/routers/reports.py`'s existing
report endpoint.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Experiment, GroundingLink, Response, Task, ToolCall, ToolSource

MAX_RECORD_REFS_PER_TOOL = 25


class ExperimentNotFound(ValueError):
    pass


async def generate_methods_section(db: AsyncSession, experiment_id: uuid.UUID) -> str:
    """Real Methods paragraph for one Experiment: every tool actually
    called (via real ToolCall rows, not the tool roster's full menu --
    a tool bound to the agent but never invoked in this experiment
    doesn't belong in its Methods section), how many times, and which
    real record IDs it grounded (via GroundingLink), scoped strictly to
    this experiment's own Tasks."""
    experiment = await db.get(Experiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFound(f"No experiment found with id {experiment_id}")

    tool_call_stmt = (
        select(ToolSource.name, ToolCall.status)
        .join(ToolCall, ToolCall.tool_source_id == ToolSource.id)
        .join(Task, ToolCall.task_id == Task.id)
        .where(Task.experiment_id == experiment_id)
    )
    tool_call_rows = (await db.execute(tool_call_stmt)).all()

    call_counts: dict[str, int] = {}
    failed_counts: dict[str, int] = {}
    for tool_name, status in tool_call_rows:
        if status == "ok":
            call_counts[tool_name] = call_counts.get(tool_name, 0) + 1
        else:
            failed_counts[tool_name] = failed_counts.get(tool_name, 0) + 1

    ref_stmt = (
        select(ToolSource.name, GroundingLink.record_ref)
        .join(ToolCall, GroundingLink.tool_call_id == ToolCall.id)
        .join(ToolSource, ToolCall.tool_source_id == ToolSource.id)
        .join(Response, GroundingLink.response_id == Response.id)
        .join(Task, Response.task_id == Task.id)
        .where(Task.experiment_id == experiment_id)
    )
    ref_rows = (await db.execute(ref_stmt)).all()
    refs_by_tool: dict[str, set[str]] = {}
    for tool_name, record_ref in ref_rows:
        refs_by_tool.setdefault(tool_name, set()).add(record_ref)

    title = experiment.name or f"Experiment {experiment.id}"
    lines = [f"# Methods -- {title}", ""]

    if not call_counts and not failed_counts:
        lines.append("No tool calls were recorded for this experiment yet -- nothing to report.")
        return "\n".join(lines)

    lines.append(
        "Computational analyses in this experiment were performed using the OpenBioLab research "
        "platform (https://github.com/RohanV01/AI-BioScientist), which executes real, versioned "
        "computational tools and data-source queries via an audited tool-call log; every source "
        "below was actually invoked, not assumed available."
    )
    lines.append("")
    lines.append("## Tools and data sources used")
    for tool_name in sorted(call_counts):
        count = call_counts[tool_name]
        refs = sorted(refs_by_tool.get(tool_name, set()))
        ref_text = ""
        if refs:
            shown = refs[:MAX_RECORD_REFS_PER_TOOL]
            more = f", and {len(refs) - MAX_RECORD_REFS_PER_TOOL} more" if len(refs) > MAX_RECORD_REFS_PER_TOOL else ""
            ref_text = f" Cited records: {', '.join(shown)}{more}."
        lines.append(f"- **{tool_name}**: {count} call{'s' if count != 1 else ''}.{ref_text}")

    if failed_counts:
        lines.append("")
        lines.append(
            "## Failed or timed-out calls (excluded from results above)"
        )
        for tool_name in sorted(failed_counts):
            lines.append(f"- **{tool_name}**: {failed_counts[tool_name]} failed/timed-out call(s), not used in any reported result.")

    return "\n".join(lines)
