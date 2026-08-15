"""Seeds one Org + the one master Agent for local dev, matching whatever
scripts/bootstrap_mattermost.sh created (docs/10-build-plan.md). Also wires
TOOL_BINDING rows for every tool source named --tools (default: pubmed),
creating the ToolSource if it doesn't exist yet. Idempotent -- safe to
re-run (updates the bot token/name/tool bindings if they changed).

There's exactly one Agent per org now (the architecture pivot, see
07-system-architecture.md) -- this script no longer takes a --cluster
flag; "cluster" on the Agent model is vestigial post-pivot
(06-data-model.md).

Usage:
  .venv/bin/python scripts/seed_dev_data.py \\
    --team-id <mattermost_team_id> --bot-user-id <bot_user_id> \\
    --bot-token <bot_access_token> [--name "AI Scientist"] [--tools pubmed]
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import async_session  # noqa: E402
from app.models import Agent, Org, ToolBinding, ToolSource  # noqa: E402
from app.vault import encrypt  # noqa: E402

# name -> (category, access_model, mcp_server_ref) for tool sources this
# script knows how to create. Matches app/tool_roster.py's TOOL_BUILDERS
# keys -- add an entry here when you add one there.
KNOWN_TOOL_SOURCES = {
    "pubmed": ("literature", "free_public", "in-process:app.tools.pubmed"),
    "chembl": ("drug_discovery", "free_public", "in-process:app.tools.chembl"),
    "open_targets": ("drug_discovery", "free_public", "in-process:app.tools.open_targets"),
    "literature_discovery": ("literature", "free_public", "in-process:app.tools.literature_discovery"),
}


async def main(team_id: str, bot_user_id: str, bot_token: str, name: str, tool_names: list[str]) -> None:
    async with async_session() as db:
        result = await db.execute(select(Org).where(Org.mattermost_team_id == team_id))
        org = result.scalar_one_or_none()
        if org is None:
            org = Org(name="AI Scientist (dev)", mattermost_team_id=team_id)
            db.add(org)
            await db.flush()
            print(f"created org {org.id}")
        else:
            print(f"org already exists: {org.id}")

        result = await db.execute(
            select(Agent).where(Agent.mattermost_bot_user_id == bot_user_id)
        )
        agent = result.scalar_one_or_none()
        encrypted_token = encrypt(bot_token) if bot_token else None
        if agent is None:
            agent = Agent(
                org_id=org.id,
                name=name,
                mattermost_bot_user_id=bot_user_id,
                encrypted_mattermost_bot_token=encrypted_token,
                cluster="master",  # vestigial post-pivot, see 06-data-model.md
                active=True,
            )
            db.add(agent)
            await db.flush()
            print(f"created agent {agent.id} ({name})")
        else:
            agent.name = name
            if encrypted_token:
                agent.encrypted_mattermost_bot_token = encrypted_token
            print(f"agent already exists, updated: {agent.id}")

        for tool_name in tool_names:
            result = await db.execute(select(ToolSource).where(ToolSource.name == tool_name))
            tool_source = result.scalar_one_or_none()
            if tool_source is None:
                if tool_name not in KNOWN_TOOL_SOURCES:
                    print(f"  skipping unknown tool source {tool_name!r} (add it to KNOWN_TOOL_SOURCES)")
                    continue
                category, access_model, mcp_ref = KNOWN_TOOL_SOURCES[tool_name]
                tool_source = ToolSource(
                    name=tool_name, category=category, access_model=access_model,
                    requires_credential=False, mcp_server_ref=mcp_ref,
                )
                db.add(tool_source)
                await db.flush()
                print(f"  created tool_source {tool_name!r}")

            result = await db.execute(
                select(ToolBinding).where(
                    ToolBinding.agent_id == agent.id, ToolBinding.tool_source_id == tool_source.id
                )
            )
            if result.scalar_one_or_none() is None:
                db.add(ToolBinding(agent_id=agent.id, tool_source_id=tool_source.id, binding_type="mcp"))
                print(f"  bound {tool_name!r} to agent")
            else:
                print(f"  {tool_name!r} already bound to agent")

        await db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--bot-user-id", required=True)
    parser.add_argument("--bot-token", default="", help="Mattermost personal access token for this bot")
    parser.add_argument("--name", default="AI Scientist")
    parser.add_argument("--tools", default="pubmed", help="Comma-separated tool source names to bind")
    args = parser.parse_args()
    asyncio.run(
        main(args.team_id, args.bot_user_id, args.bot_token, args.name, args.tools.split(","))
    )
