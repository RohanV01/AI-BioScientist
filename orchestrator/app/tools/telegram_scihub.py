"""Tier 3 of the full-text acquisition waterfall (see
app/tools/literature_discovery.py's download_paper): a Telegram bot that
you message a DOI/URL to and it replies with the paper's PDF.

Unlike Sci-Doc-Hub (tier 1, plain HTTP) or Camofox (tier 2, an HTTP-driven
browser), this isn't an HTTP API at all -- it's an ordinary Telegram chat.
Telegram's Bot API can't be used to drive this because bots cannot message
other bots; only a real logged-in *user* account can open a chat with an
arbitrary bot and read its replies. That's what Telethon (an MTProto user
client, not the Bot API) gives us here.

One-time setup, done by a human, not this module:
  1. Register an app at https://my.telegram.org -> API_ID/API_HASH.
  2. Run `python scripts/telegram_login.py` once, interactively (phone
     number + the login code Telegram sends) -- it prints a session
     string to save as TELEGRAM_SESSION_STRING in .env. After that,
     everything below is unattended.
"""
import asyncio
from typing import Any

from app.config import settings

# How long to wait for the bot to reply with a PDF before giving up.
_REPLY_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 2.0


def _telegram_configured() -> bool:
    return bool(
        settings.telegram_api_id
        and settings.telegram_api_hash
        and settings.telegram_session_string
        and settings.telegram_scihub_bot_username
    )


async def _wait_for_pdf_reply(client: Any, bot: Any, after_id: int) -> bytes | None:
    deadline = asyncio.get_event_loop().time() + _REPLY_TIMEOUT_SECONDS
    while asyncio.get_event_loop().time() < deadline:
        async for message in client.iter_messages(bot, min_id=after_id, limit=5):
            filename = (getattr(message.file, "name", "") or "").lower()
            if message.document and filename.endswith(".pdf"):
                return await client.download_media(message, file=bytes)
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    return None


async def try_telegram_scihub_bot(doi: str) -> bytes | None:
    """Message the DOI to the configured Sci-Hub Telegram bot and wait for
    its PDF reply. Returns the PDF bytes, or None if not configured, not
    logged in, or the bot didn't reply with a PDF in time.
    """
    if not _telegram_configured():
        return None

    # Imported lazily so the orchestrator doesn't hard-require telethon
    # when this tier is unconfigured/unused.
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(
        StringSession(settings.telegram_session_string),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.connect()
    try:
        if not await client.is_user_authorized():
            # TELEGRAM_SESSION_STRING is missing/expired -- re-run
            # scripts/telegram_login.py to get a fresh one. Can't
            # interactively prompt for a login code from inside a running
            # server process, so this tier just declines rather than hangs.
            return None

        bot = await client.get_entity(settings.telegram_scihub_bot_username)
        sent = await client.send_message(bot, f"https://doi.org/{doi}")
        return await _wait_for_pdf_reply(client, bot, after_id=sent.id)
    finally:
        await client.disconnect()
