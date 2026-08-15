"""The Claude Code/Codex Runner (docs/07-system-architecture.md): invokes
the actual agentic loop for a task, scoped tightly to just the tools the
agent is bound to -- explicitly NOT inheriting the host's full Claude Code
configuration (personal tools/plugins/connectors), which is the default
behavior of a bare `query()` call and is wrong for a backend service
running on someone else's behalf.
"""
import re
import tempfile
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

from app.tools.pubmed import build_pubmed_mcp_server

PMID_RE = re.compile(r"PMID (\d+)")

LITERATURE_AGENT_SYSTEM_PROMPT = """\
You are the Literature Agent for AI Scientist, a research platform.

Hard rule, non-negotiable: every factual claim you make about a paper
(its existence, findings, authors, journal, year) must come from a
search_articles tool result. Never state a PMID, title, finding, or any
other detail you did not receive from a tool call -- this includes DOIs,
links, page numbers, or anything else the tool did not return, even if you
recognize the paper and believe you know that detail. If the tool result
doesn't include something, leave it out rather than filling it in from
memory. If you cannot find a relevant paper, say so plainly instead of
guessing.

Only discuss papers you actually cite by PMID in your answer -- don't
mention a search turned up other results if you're not going to use them.

Be concise. Answer the question, cite what backs each claim, PMID only
(e.g. "PMID 12345678") -- no DOIs, no external links.
"""


@dataclass
class RunnerToolCall:
    """One real tool invocation the agent made -- persisted as a ToolCall
    row by the caller (docs/06-data-model.md), not just kept in memory,
    so GroundingLink rows can point at something real rather than a
    citation that's disconnected from any actual tool call."""

    tool_name: str
    request: dict
    result_text: str


@dataclass
class RunnerCitation:
    pmid: str
    label: str
    tool_call_index: int  # index into RunnerResult.tool_calls -- which call backs this citation


@dataclass
class RunnerResult:
    body: str
    citations: list[RunnerCitation]
    provenance_type: str  # "grounded" | "synthesis" | "ungroundable"
    tool_calls: list[RunnerToolCall] = field(default_factory=list)


async def run_literature_agent(user_message: str) -> RunnerResult:
    pubmed_server = build_pubmed_mcp_server()

    options = ClaudeAgentOptions(
        system_prompt=LITERATURE_AGENT_SYSTEM_PROMPT,
        mcp_servers={"pubmed": pubmed_server},
        allowed_tools=["mcp__pubmed__search_articles"],
        # No filesystem/bash/etc access -- this agent only ever needs the
        # one tool above. cwd is a scratch dir so nothing in the actual
        # repo is reachable even if something tried.
        tools=[],
        # CRITICAL isolation setting -- without this, `allowed_tools` above
        # is not enough: the SDK's default (setting_sources=None) still
        # loads ~/.claude/settings.json and every personal MCP connector
        # configured there (found the hard way: a real run used the
        # developer's own personal PubMed/Gmail/etc connectors instead of
        # the tool defined above). []  disables all filesystem settings --
        # the SDK's own documented "isolation mode."
        setting_sources=[],
        permission_mode="bypassPermissions",  # headless service, no human to prompt
        max_turns=6,
        cwd=tempfile.mkdtemp(prefix="ai-scientist-literature-agent-"),
    )

    # tool_use_id -> {"name": ..., "input": ...}, paired with its result
    # once the matching ToolResultBlock arrives.
    pending_calls: dict[str, dict] = {}
    tool_calls: list[RunnerToolCall] = []
    final_text_parts: list[str] = []

    async for msg in query(prompt=user_message, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    final_text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    pending_calls[block.id] = {"name": block.name, "input": block.input}
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
                            request=call_info["input"],
                            result_text="\n".join(text_parts),
                        )
                    )
        elif isinstance(msg, ResultMessage):
            if msg.is_error:
                return RunnerResult(
                    body=f"Something went wrong answering this: {msg.result or 'unknown error'}",
                    citations=[],
                    provenance_type="ungroundable",
                    tool_calls=tool_calls,
                )

    body = "\n".join(final_text_parts).strip()

    # Precision matters here: a citation should mean "this specific claim in
    # the answer traces to this PMID," not "this PMID appeared somewhere in
    # a tool call's raw results." Intersect what the tools actually returned
    # (the only PMIDs we can vouch for) with what the final answer actually
    # discusses -- excludes search results the model saw but didn't use,
    # which would otherwise inflate the grounding block with noise.
    pmids_in_answer = set(re.findall(r"PMID (\d+)", body))

    citations: list[RunnerCitation] = []
    seen_pmids: set[str] = set()
    for idx, tc in enumerate(tool_calls):
        for pmid in PMID_RE.findall(tc.result_text):
            if pmid in pmids_in_answer and pmid not in seen_pmids:
                seen_pmids.add(pmid)
                citations.append(
                    RunnerCitation(pmid=pmid, label=f"PubMed PMID {pmid}", tool_call_index=idx)
                )

    if not body:
        return RunnerResult(
            body="I wasn't able to produce an answer for this.",
            citations=[],
            provenance_type="ungroundable",
            tool_calls=tool_calls,
        )
    if citations:
        return RunnerResult(
            body=body, citations=citations, provenance_type="grounded", tool_calls=tool_calls
        )
    return RunnerResult(body=body, citations=[], provenance_type="synthesis", tool_calls=tool_calls)
