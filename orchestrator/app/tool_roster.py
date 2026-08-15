"""Builds the master agent's tool roster from TOOL_BINDING rows
(docs/06-data-model.md) rather than hardcoding one tool per agent
function -- this is what "growing the roster" (docs/10-build-plan.md
Phase 3+) actually means in code: add a builder here and a TOOL_BINDING
row in the DB, nothing else changes.

Adding a new tool source means adding an entry to TOOL_BUILDERS (and, for
external MCP servers rather than in-process SDK tools, an McpServerConfig
instead of a create_sdk_mcp_server() call) -- the Runner and webhook
handler don't change.
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, ToolBinding, ToolSource
from app.tools.chembl import build_chembl_mcp_server
from app.tools.literature_discovery import build_literature_discovery_mcp_server
from app.tools.open_targets import build_open_targets_mcp_server
from app.tools.pubmed import build_pubmed_mcp_server

# tool_source.name -> (mcp_server_name, builder_fn, list of allowed tool names)
TOOL_BUILDERS = {
    "pubmed": ("pubmed", build_pubmed_mcp_server, ["mcp__pubmed__search_articles"]),
    "chembl": (
        "chembl", build_chembl_mcp_server,
        ["mcp__chembl__compound_search", "mcp__chembl__get_bioactivity"],
    ),
    "open_targets": (
        "open_targets", build_open_targets_mcp_server,
        ["mcp__open_targets__search_entities", "mcp__open_targets__get_target_disease_associations"],
    ),
    "literature_discovery": (
        "literature_discovery", build_literature_discovery_mcp_server,
        ["mcp__literature_discovery__discover_papers", "mcp__literature_discovery__check_scihub_availability"],
    ),
}


@dataclass
class ToolRoster:
    mcp_servers: dict
    allowed_tools: list[str]
    tool_source_by_mcp_name: dict[str, "ToolSource"]  # mcp server name -> ToolSource row


async def build_tool_roster(db: AsyncSession, agent: Agent) -> ToolRoster:
    result = await db.execute(
        select(ToolSource)
        .join(ToolBinding, ToolBinding.tool_source_id == ToolSource.id)
        .where(ToolBinding.agent_id == agent.id)
    )
    tool_sources = result.scalars().all()

    mcp_servers: dict = {}
    allowed_tools: list[str] = []
    tool_source_by_mcp_name: dict[str, ToolSource] = {}

    for ts in tool_sources:
        entry = TOOL_BUILDERS.get(ts.name)
        if entry is None:
            continue  # tool_source exists but has no in-process builder yet -- skip, don't crash
        mcp_name, builder, tools = entry
        mcp_servers[mcp_name] = builder()
        allowed_tools.extend(tools)
        tool_source_by_mcp_name[mcp_name] = ts

    return ToolRoster(
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        tool_source_by_mcp_name=tool_source_by_mcp_name,
    )
