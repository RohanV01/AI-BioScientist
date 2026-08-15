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

# name -> (category, access_model, mcp_server_ref, requires_expert_review)
# for tool sources this script knows how to create. Matches
# app/tool_roster.py's TOOL_BUILDERS keys -- add an entry here when you
# add one there. requires_expert_review is docs/05-ux-behavior.md
# Section 4's marker: True for clinical/regulatory-sensitive sources
# (clinical variant databases, trial registries, drug labels, FAERS).
KNOWN_TOOL_SOURCES = {
    "pubmed": ("literature", "free_public", "in-process:app.tools.pubmed", False),
    "chembl": ("drug_discovery", "free_public", "in-process:app.tools.chembl", False),
    "open_targets": ("drug_discovery", "free_public", "in-process:app.tools.open_targets", False),
    "literature_discovery": ("literature", "free_public", "in-process:app.tools.literature_discovery", False),
    "ensembl": ("genomics", "free_public", "in-process:app.tools.ensembl", False),
    "uniprot": ("genomics", "free_public", "in-process:app.tools.uniprot", False),
    "clinvar": ("genomics", "free_public", "in-process:app.tools.clinvar", True),
    "gnomad": ("genomics", "free_public", "in-process:app.tools.gnomad", False),
    "ontologies": ("ontologies", "free_public", "in-process:app.tools.ontologies", False),
    "kegg": ("systems_biology", "free_public", "in-process:app.tools.kegg", False),
    "reactome": ("systems_biology", "free_public", "in-process:app.tools.reactome", False),
    "string": ("systems_biology", "free_public", "in-process:app.tools.string_db", False),
    "clinicaltrials": ("clinical", "free_public", "in-process:app.tools.clinicaltrials", True),
    "dailymed": ("clinical", "free_public", "in-process:app.tools.dailymed", True),
    "pdb": ("structural_biology", "free_public", "in-process:app.tools.pdb", False),
    "alphafold": ("structural_biology", "free_public", "in-process:app.tools.alphafold", False),
    # pharmgkb intentionally not here yet -- see docs/10-build-plan.md
    # Shortlist #6: PharmGKB rebranded to ClinPGx and its old public API
    # surface (api.pharmgkb.org/v1/data/*) no longer resolves/works;
    # every guessed replacement path on clinpgx.org returns the SPA's
    # HTML shell instead of JSON (200 for any path, no clean 404 to
    # signal a wrong guess), so this needs real API docs, not more
    # trial and error.
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
            if tool_name not in KNOWN_TOOL_SOURCES:
                if tool_source is None:
                    print(f"  skipping unknown tool source {tool_name!r} (add it to KNOWN_TOOL_SOURCES)")
                    continue
            else:
                category, access_model, mcp_ref, requires_review = KNOWN_TOOL_SOURCES[tool_name]
                if tool_source is None:
                    tool_source = ToolSource(
                        name=tool_name, category=category, access_model=access_model,
                        requires_credential=False, mcp_server_ref=mcp_ref,
                        requires_expert_review=requires_review,
                    )
                    db.add(tool_source)
                    await db.flush()
                    print(f"  created tool_source {tool_name!r}")
                elif tool_source.requires_expert_review != requires_review:
                    # Keeps an already-created row in sync with
                    # KNOWN_TOOL_SOURCES if the flag changes later (this is
                    # how clinvar picked up requires_expert_review=True
                    # after being wired before this convention existed).
                    tool_source.requires_expert_review = requires_review
                    print(f"  updated {tool_name!r}.requires_expert_review -> {requires_review}")

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
