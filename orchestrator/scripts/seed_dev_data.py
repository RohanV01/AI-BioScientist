"""Seeds one Org + one Agent for local dev, matching whatever
scripts/bootstrap_mattermost.sh created (docs/10-build-plan.md Phase 0/1).
Idempotent -- safe to re-run (updates the bot token if it changed).

Usage:
  .venv/bin/python scripts/seed_dev_data.py \\
    --team-id <mattermost_team_id> --bot-user-id <bot_user_id> \\
    --bot-token <bot_access_token> [--name "Literature Agent"] [--cluster literature]
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import async_session  # noqa: E402
from app.models import Agent, Org  # noqa: E402
from app.vault import encrypt  # noqa: E402


async def main(team_id: str, bot_user_id: str, bot_token: str, name: str, cluster: str) -> None:
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
                cluster=cluster,
                active=True,
            )
            db.add(agent)
            await db.flush()
            print(f"created agent {agent.id} ({name}, cluster={cluster})")
        else:
            agent.name = name
            agent.cluster = cluster
            if encrypted_token:
                agent.encrypted_mattermost_bot_token = encrypted_token
            print(f"agent already exists, updated: {agent.id}")

        await db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--bot-user-id", required=True)
    parser.add_argument("--bot-token", default="", help="Mattermost personal access token for this bot")
    parser.add_argument("--name", default="Literature Agent")
    parser.add_argument("--cluster", default="literature")
    args = parser.parse_args()
    asyncio.run(main(args.team_id, args.bot_user_id, args.bot_token, args.name, args.cluster))
