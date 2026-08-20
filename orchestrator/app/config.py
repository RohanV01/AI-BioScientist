"""Settings loaded from environment / .env at the repo root.

See ../../.env.example for the full set of variables and what each does.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    orchestrator_db_url: str = (
        "postgresql+asyncpg://aiscientist:dev_only_change_me@localhost:5432/orchestrator"
    )
    mattermost_url: str = "http://localhost:8065"
    mattermost_webhook_secret: str = ""  # verifies inbound Outgoing Webhook calls
    anthropic_api_key: str = ""
    credential_vault_key: str = ""
    # Flat, one-DOI-per-line Sci-Hub archive index used for the local
    # grep -F -x waterfall check in app/tools/literature_discovery.py --
    # NOT the 32GB scihub.sql dump (too slow to query directly, see
    # docs/10-build-plan.md's architecture pivot note).
    scihub_doi_index_path: str = (
        "../data/Databases/scihub/sci-hub-doi-2022-02-12.txt"
    )
    # Base URL for links the Orchestrator posts into Mattermost that a
    # human clicks from their own browser (docs/05-ux-behavior.md Section 3's
    # full-report link-out) -- NOT the same as mattermost_url, which is
    # how the Orchestrator itself reaches Mattermost's API. Defaults to
    # localhost since local dev browses from the host, not a container.
    orchestrator_public_url: str = "http://localhost:8000"

    # Full-text acquisition waterfall (app/tools/literature_discovery.py
    # download_paper) -- tried in order, first one that returns a PDF wins.
    # 1) Sci-Doc-Hub MCP server: https://github.com/JackKuo666/Sci-Hub-MCP-Server
    #    (Vault/Open-Source-Projects/sci-doc-hub-mcp-server-2026-08-11.md)
    sci_doc_hub_mcp_url: str = ""  # PLACEHOLDER -- fill in deployed server URL
    # 2) Camofox stealth headless browser, only reached if (1) fails/is unset:
    #    https://github.com/jo-inc/camofox-browser
    #    (Vault/AI-Tools/camofox-browser-stealth-headless-browser-2026-08-16.md)
    #    Real API per that repo's README: POST /tabs to open+navigate,
    #    POST /tabs/:id/evaluate to read the embedded PDF's src out of the
    #    DOM, GET /tabs/:id/snapshot + POST /tabs/:id/type + .../click as a
    #    fallback that fills the "enter your reference" form like a human
    #    would, DELETE /tabs/:id to clean up -- see _try_camofox in
    #    literature_discovery.py.
    camofox_api_url: str = ""  # PLACEHOLDER -- fill in deployed server URL, e.g. http://localhost:9377
    # Only needed if the Camofox server sets CAMOFOX_ACCESS_KEY -- sent as
    # `Authorization: Bearer <key>` on every request. Leave blank for a
    # loopback-only/no-auth deployment.
    camofox_access_key: str = ""
    # Comma-separated Sci-Hub mirrors Camofox tries in order (some mirrors
    # go down/get blocked at any given time) -- e.g.
    # "https://sci-hub.se,https://sci-hub.ren,https://sci-hub.st"
    scihub_mirror_urls: str = ""  # PLACEHOLDER -- fill in your working mirrors
    # 3) Telegram Sci-Hub bot, only reached if (1) and (2) both fail/are
    #    unset: message a DOI/URL to a Telegram bot that replies with the
    #    paper's PDF as a document attachment. Unlike (1)/(2) this is not
    #    an HTTP API -- it needs a real logged-in Telegram user session
    #    (Telethon), since only a user account can message an arbitrary
    #    bot and read its replies. One-time setup: register an app at
    #    https://my.telegram.org for TELEGRAM_API_ID/TELEGRAM_API_HASH,
    #    then run `python scripts/telegram_login.py` once (interactive --
    #    phone number + login code) to produce TELEGRAM_SESSION_STRING.
    #    See README.md's Getting Started for the full walkthrough.
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_session_string: str = ""
    # The Sci-Hub bot's own @username -- https://t.me/scihubot. Override if
    # you use a different mirror bot.
    telegram_scihub_bot_username: str = "scihubot"
    # Where downloaded PDFs are saved, one file per DOI.
    papers_download_dir: str = "../data/Databases/papers"


settings = Settings()
