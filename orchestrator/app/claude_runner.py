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
   compound, a target, a disease) must come from a tool result -- never
   state an ID, title, finding, or any other detail a tool didn't actually
   return, even if you recognize it and believe you know that detail. If
   you cannot find something relevant, say so plainly instead of guessing.
   Include each record's ID inline, next to the claim it backs (e.g. "KRAS
   is linked to Noonan syndrome (MONDO_0018997)", "PMID 12345678", "ChEMBL
   ID CHEMBL941") -- a name or score alone, without the ID, cannot be
   verified against the tool's actual output and will not count as
   grounded. Put the ID on every row of a table too, not just the first
   mention.

If a task genuinely doesn't need a tool (e.g. a clarifying question back to
the researcher), you can skip straight to a short response -- the three
stages are for tasks that need real lookups, not a rigid format for
everything.
"""

# Record-ID patterns recognized in tool result text, for grounding
# citation extraction. Add an entry here whenever a new tool source is
# wired (docs/10-build-plan.md Phase 3+) if it returns a distinctly-
# formatted record ID -- this is the one place citation extraction needs
# to know about a new tool, everything else in this file is tool-agnostic.
RECORD_REF_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("PubMed PMID {}", re.compile(r"PMID (\d+)")),
    ("ChEMBL ID {}", re.compile(r"\b(CHEMBL\d+)\b")),
    # Shared between open_targets.py and ensembl.py -- both surface Ensembl
    # gene IDs, so the label stays tool-agnostic rather than naming one.
    ("Ensembl Gene ID {}", re.compile(r"\b(ENSG\d{11})\b")),
    ("Open Targets Disease ID {}", re.compile(r"\b(MONDO_\d+|EFO_\d+|Orphanet_\d+|HP_\d+)\b")),
    ("DOI {}", re.compile(r"\b(10\.\d{4,9}/[A-Za-z0-9._;()/-]+)")),
    (
        "UniProt ID {}",
        re.compile(r"\b((?:[OPQ][0-9][A-Z0-9]{3}[0-9])|(?:[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:[A-Z][A-Z0-9]{2}[0-9])?))\b"),
    ),
]


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
        # CRITICAL, both of these, found the hard way (see 07-system-architecture.md):
        # setting_sources=[] blocks ~/.claude/settings.json-configured connectors
        # (Phase 1's leak: personal PubMed/Gmail connectors). It does NOT block
        # account-linked connectors tied to the authenticated Claude.ai session
        # itself (Phase 3's leak, found adding ChEMBL: the agent silently used
        # the developer's personal claude_ai_ChEMBL connector instead of the
        # wired tool). strict_mcp_config=True closes that second gap -- only
        # what's explicitly in mcp_servers below is available, full stop.
        setting_sources=[],
        strict_mcp_config=True,
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

    # Generalized citation extraction (fixed in Phase 3 when ChEMBL was
    # added -- Phase 2's version was PubMed-only, see the build plan).
    # RECORD_REF_PATTERNS maps a label template to a regex whose one
    # capture group is the bare record ID as it appears in a tool's
    # result_text. A citation only counts if that same bare ID string
    # also appears somewhere in the final answer (substring match, not
    # requiring the tool's exact "label: ID" phrasing to be echoed back --
    # the model may write "CHEMBL941" without repeating "ChEMBL ID").
    citations: list[RunnerCitation] = []
    seen: set[str] = set()
    for idx, tc in enumerate(tool_calls):
        for label_template, pattern in RECORD_REF_PATTERNS:
            for record_id in pattern.findall(tc.result_text):
                if record_id in seen or record_id not in body:
                    continue
                seen.add(record_id)
                citations.append(
                    RunnerCitation(
                        record_ref=record_id, label=label_template.format(record_id), tool_call_index=idx
                    )
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
