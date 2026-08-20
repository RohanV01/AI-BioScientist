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
    #    GET /tabs/:id/downloads for captured downloads, GET /tabs/:id/snapshot
    #    + POST /tabs/:id/click to click a save/download control, DELETE
    #    /tabs/:id to clean up -- see _try_camofox in literature_discovery.py.
    camofox_api_url: str = ""  # PLACEHOLDER -- fill in deployed server URL, e.g. http://localhost:9377
    # Only needed if the Camofox server sets CAMOFOX_ACCESS_KEY -- sent as
    # `Authorization: Bearer <key>` on every request. Leave blank for a
    # loopback-only/no-auth deployment.
    camofox_access_key: str = ""
    # Where downloaded PDFs are saved, one file per DOI.
    papers_download_dir: str = "../data/Databases/papers"


settings = Settings()
