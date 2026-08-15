"""The Claude Code/Codex Runner (docs/07-system-architecture.md): the
master agent's Plan -> Execute -> Synthesize loop. One runner, whatever
tools happen to be wired -- not one function per domain (see the
architecture pivot note in docs/10-build-plan.md).
"""
import re
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from app.tool_roster import ToolRoster

MASTER_AGENT_SYSTEM_PROMPT = """\
You are the AI Scientist research agent. A researcher will ask you something --
answer it by using the tools available to you, never from memory alone for
anything you could instead look up.

Work in three explicit stages, in this order, every time:

1. PLAN. Before calling any tool, write a short methodology: what you
   understand the request to need, and which tool(s) you intend to use and
   why. Keep it concrete ("I'll search PubMed for X, then Y") not vague
   ("I'll do some research"). This is shown to the researcher as-is, before
   you've executed anything -- it's how they know what you're about to do
   and can catch a wrong plan before it runs.
2. EXECUTE. Call the tools your plan named. If a tool result changes what
   you need to do next (nothing useful came back, or it points somewhere
   else), say so and adapt -- don't silently execute a different plan than
   the one you stated.
3. SYNTHESIZE. Write the final answer from what the tools actually
   returned. Every factual claim about a specific record (a paper, a
   compound, a target) must come from a tool result -- never state an ID,
   title, finding, or any other detail a tool didn't actually return, even
   if you recognize it and believe you know that detail. If you cannot find
   something relevant, say so plainly instead of guessing.

If a task genuinely doesn't need a tool (e.g. a clarifying question back to
the researcher), you can skip straight to a short response -- the three
stages are for tasks that need real lookups, not a rigid format for
everything.
"""

PMID_RE = re.compile(r"PMID (\d+)")


@dataclass
class RunnerToolCall:
    """One real tool invocation the agent made -- persisted as a ToolCall
    row by the caller (docs/06-data-model.md)."""

    tool_name: str  # full mcp__<server>__<tool> name
    mcp_server_name: str  # just <server> -- maps back to a ToolSource via the roster
    request: dict
    result_text: str


@dataclass
class RunnerCitation:
    record_ref: str
    label: str
    tool_call_index: int  # index into RunnerResult.tool_calls -- which call backs this citation


@dataclass
class RunnerResult:
    plan: str
    body: str
    citations: list[RunnerCitation]
    provenance_type: str  # "grounded" | "synthesis" | "ungroundable"
    tool_calls: list[RunnerToolCall] = field(default_factory=list)


def _mcp_server_name_from_tool_name(tool_name: str) -> str:
    # ToolUseBlock.name is "mcp__<server>__<tool>" for MCP-provided tools.
    parts = tool_name.split("__")
    return parts[1] if len(parts) >= 3 and parts[0] == "mcp" else ""


async def run_agent(
    user_message: str,
    roster: ToolRoster,
    on_plan: Callable[[str], Awaitable[None]] | None = None,
) -> RunnerResult:
    options = ClaudeAgentOptions(
        system_prompt=MASTER_AGENT_SYSTEM_PROMPT,
        mcp_servers=roster.mcp_servers,
        allowed_tools=roster.allowed_tools,
        tools=[],  # no filesystem/bash/etc -- only the wired roster
        # CRITICAL: without this, the SDK loads the host's ~/.claude/settings.json
        # and every personal MCP connector configured there instead of just the
        # roster above -- found the hard way in Phase 1, see 07-system-architecture.md.
        setting_sources=[],
        permission_mode="bypassPermissions",  # headless service, no human to prompt
        max_turns=10,
        cwd=tempfile.mkdtemp(prefix="ai-scientist-agent-"),
    )

    pending_calls: dict[str, dict] = {}
    tool_calls: list[RunnerToolCall] = []
    plan_text_parts: list[str] = []
    final_text_parts: list[str] = []
    plan_announced = False

    async for msg in query(prompt=user_message, options=options):
        if isinstance(msg, AssistantMessage):
            has_tool_use_this_message = any(isinstance(b, ToolUseBlock) for b in msg.content)
            for block in msg.content:
                if isinstance(block, TextBlock):
                    if not plan_announced:
                        plan_text_parts.append(block.text)
                    else:
                        final_text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    pending_calls[block.id] = {"name": block.name, "input": block.input}
            if has_tool_use_this_message and not plan_announced:
                # First message that actually calls a tool marks the plan as
                # "announced" -- everything before this was the PLAN stage;
                # everything from here on (including this message's own text,
                # if any, e.g. narration alongside a tool call) counts as
                # execution/synthesis text, not more plan.
                plan_announced = True
                if on_plan is not None:
                    plan_text = "\n".join(plan_text_parts).strip()
                    if plan_text:
                        await on_plan(plan_text)
        elif isinstance(msg, UserMessage):
            content = msg.content if isinstance(msg.content, list) else []
            for block in content:
                if isinstance(block, ToolResultBlock):
                    call_info = pending_calls.pop(block.tool_use_id, None)
                    if call_info is None:
                        continue
                    inner = block.content
                    text_parts = []
                    if isinstance(inner, str):
                        text_parts.append(inner)
                    elif isinstance(inner, list):
                        for c in inner:
                            if isinstance(c, dict) and c.get("type") == "text":
                                text_parts.append(c["text"])
                            elif isinstance(c, TextBlock):
                                text_parts.append(c.text)
                    tool_calls.append(
                        RunnerToolCall(
                            tool_name=call_info["name"],
                            mcp_server_name=_mcp_server_name_from_tool_name(call_info["name"]),
                            request=call_info["input"],
                            result_text="\n".join(text_parts),
                        )
                    )
        elif isinstance(msg, ResultMessage):
            if msg.is_error:
                return RunnerResult(
                    plan="\n".join(plan_text_parts).strip(),
                    body=f"Something went wrong answering this: {msg.result or 'unknown error'}",
                    citations=[],
                    provenance_type="ungroundable",
                    tool_calls=tool_calls,
                )

    plan = "\n".join(plan_text_parts).strip()
    body = "\n".join(final_text_parts).strip() or plan  # no-tool-needed replies land entirely in "plan"

    # Citation extraction is PubMed-shaped today (PMID regex) because
    # PubMed is the only wired tool -- this needs to generalize once
    # Phase 3 adds tools with different record-ID formats (ChEMBL IDs,
    # PDB IDs, etc.). Tracked as a known gap, not solved here.
    pmids_in_answer = set(re.findall(r"PMID (\d+)", body))
    citations: list[RunnerCitation] = []
    seen: set[str] = set()
    for idx, tc in enumerate(tool_calls):
        for pmid in PMID_RE.findall(tc.result_text):
            if pmid in pmids_in_answer and pmid not in seen:
                seen.add(pmid)
                citations.append(
                    RunnerCitation(record_ref=pmid, label=f"PubMed PMID {pmid}", tool_call_index=idx)
                )

    if not body:
        return RunnerResult(
            plan=plan,
            body="I wasn't able to produce an answer for this.",
            citations=[],
            provenance_type="ungroundable",
            tool_calls=tool_calls,
        )
    provenance = "grounded" if citations else "synthesis"
    return RunnerResult(plan=plan, body=body, citations=citations, provenance_type=provenance, tool_calls=tool_calls)
