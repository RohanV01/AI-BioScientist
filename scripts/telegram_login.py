#!/usr/bin/env python3
"""One-time interactive login for the Telegram Sci-Hub bot fallback
(app/tools/telegram_scihub.py's Tier 3 of download_paper's acquisition
waterfall).

Why this has to be run by a human, once, outside the orchestrator:
Telegram's Bot API can't message another bot -- only a real logged-in
*user* account can open a chat with an arbitrary bot and read its
replies. This script logs in as that user account (via Telethon, an
MTProto client) and prints a portable session string. Save that string
as TELEGRAM_SESSION_STRING in .env; the orchestrator reuses it from then
on and never needs to prompt for a login code itself.

Prerequisites:
  1. Register an app at https://my.telegram.org -> API development tools
     -> note the api_id and api_hash it gives you.
  2. `pip install telethon` (not required inside the orchestrator's own
     venv/container for this step -- just wherever you run this script).

Usage:
    python scripts/telegram_login.py

You'll be prompted for:
  - the api_id / api_hash from step 1 above
  - your phone number (with country code, e.g. +15551234567)
  - the login code Telegram sends you (via the Telegram app or SMS)
  - your 2FA password, only if you have two-step verification enabled

It then prints a session string -- copy that into .env as
TELEGRAM_SESSION_STRING. Treat it like a password: anyone with this
string can act as your Telegram account until you revoke the session
from Telegram's own Settings -> Devices.
"""
import asyncio

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    print(__doc__)
    api_id = int(input("api_id: ").strip())
    api_hash = input("api_hash: ").strip()

    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        # TelegramClient's async context manager handles the interactive
        # phone/code/2FA-password prompts itself on first connect.
        session_string = client.session.save()

    print("\nLogin successful. Add this line to .env:\n")
    print(f"TELEGRAM_API_ID={api_id}")
    print(f"TELEGRAM_API_HASH={api_hash}")
    print(f"TELEGRAM_SESSION_STRING={session_string}")
    print(
        "\nAlso set TELEGRAM_SCIHUB_BOT_USERNAME to the Sci-Hub bot's exact "
        "@handle (visible in the Telegram app for the chat you message)."
    )


if __name__ == "__main__":
    asyncio.run(main())
