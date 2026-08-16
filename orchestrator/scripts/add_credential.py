"""Adds or rotates a BYO credential for a paid/metered tool source
(docs/07-system-architecture.md's Credential Vault, Section 8 of the
research report). This is the piece that was missing: ToolSource rows
could be marked requires_credential=True and the Credential model
existed (app/models.py, app/vault.py), but there was no actual path for
an org to add one -- this is that path, for any BYO tool, not a
one-off script for a single tool or a single person's key.

The credential is encrypted before it ever touches the database
(app/vault.py) -- this script only ever holds the plaintext value in
memory for the duration of the encrypt call.

Usage:
  .venv/bin/python scripts/add_credential.py \\
    --team-id <mattermost_team_id> --tool-source huggingface \\
    --value <the-api-key> --added-by <your-name-or-email>
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import async_session  # noqa: E402
from app.models import Credential, Org, ToolSource  # noqa: E402
from app.vault import encrypt  # noqa: E402


async def main(team_id: str, tool_source_name: str, value: str, added_by: str) -> None:
    async with async_session() as db:
        org = (await db.execute(select(Org).where(Org.mattermost_team_id == team_id))).scalar_one_or_none()
        if org is None:
            print(f"No org found for mattermost_team_id={team_id!r} -- run seed_dev_data.py first.")
            return

        tool_source = (
            await db.execute(select(ToolSource).where(ToolSource.name == tool_source_name))
        ).scalar_one_or_none()
        if tool_source is None:
            print(f"No tool_source named {tool_source_name!r} -- it must exist before adding a credential for it.")
            return
        if not tool_source.requires_credential:
            print(f"Warning: tool_source {tool_source_name!r} isn't marked requires_credential=True -- adding anyway.")

        existing = (
            await db.execute(
                select(Credential).where(
                    Credential.org_id == org.id, Credential.tool_source_id == tool_source.id
                )
            )
        ).scalar_one_or_none()

        encrypted_value = encrypt(value)
        if existing is None:
            db.add(Credential(org_id=org.id, tool_source_id=tool_source.id, encrypted_value=encrypted_value, added_by=added_by))
            print(f"Added credential for {tool_source_name!r} (org {org.id}).")
        else:
            existing.encrypted_value = encrypted_value
            existing.added_by = added_by
            print(f"Rotated existing credential for {tool_source_name!r} (org {org.id}).")

        await db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--tool-source", required=True, help="ToolSource.name this credential is for")
    parser.add_argument("--value", required=True, help="The plaintext credential value (API key/token)")
    parser.add_argument("--added-by", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.team_id, args.tool_source, args.value, args.added_by))
