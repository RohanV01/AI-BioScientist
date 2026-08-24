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
    # Verifies inbound /experiment Slash Command calls -- a *separate*
    # secret from mattermost_webhook_secret above because Mattermost
    # auto-generates its own token per integration at creation time (no way
    # to set a custom one); a Slash Command and an Outgoing Webhook can
    # never share one value.
    mattermost_experiment_command_secret: str = ""
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

    # Full-text acquisition (app/tools/literature_discovery.py
    # download_paper): Camofox stealth headless browser --
    # https://github.com/jo-inc/camofox-browser
    # (Vault/AI-Tools/camofox-browser-stealth-headless-browser-2026-08-16.md).
    # Drives the real sci-hub UI (paste DOI, click open, click the page's
    # own save button) and captures the resulting native browser download
    # -- see _try_camofox in literature_discovery.py for the verified API
    # shape (POST /tabs, GET /tabs/:id/snapshot, POST /tabs/:id/{type,
    # click,wait}, GET /tabs/:id/downloads, DELETE /tabs/:id).
    camofox_api_url: str = ""  # e.g. http://localhost:9377
    # Only needed if the Camofox server sets CAMOFOX_ACCESS_KEY -- sent as
    # `Authorization: Bearer <key>` on every request. Leave blank for a
    # loopback-only/no-auth deployment.
    camofox_access_key: str = ""
    # Comma-separated Sci-Hub mirrors Camofox tries in order (some mirrors
    # go down/get blocked at any given time) -- e.g.
    # "https://sci-hub.se,https://sci-hub.ren,https://sci-hub.st"
    scihub_mirror_urls: str = ""  # PLACEHOLDER -- fill in your working mirrors
    # Where downloaded PDFs are saved, one file per DOI. Used only as the
    # fallback when no Experiment is in scope (app/experiment_context.py) --
    # e.g. standalone tool calls outside a live agent run. A real agent run
    # always saves into that Experiment's own data/Experiments/<id>/papers/
    # instead.
    papers_download_dir: str = "../data/Databases/papers"
    # Root directory each Experiment gets its own <id>/ subfolder under
    # (papers/, findings/, papers.json manifest, conclusion.md). See the
    # Experiments plan -- this is what makes "save individual experiments in
    # a separate folder" real instead of everything landing in one shared
    # pile.
    experiments_dir: str = "../data/Experiments"

    # One-shot completion backend for read_paper's structured extraction
    # and /experiment conclude's synthesis (app/llm_backend.py) -- NOT the
    # master agent's own multi-turn loop, which always uses claude_agent_sdk
    # regardless of this setting. "auto" (default) tries anthropic_api (if
    # ANTHROPIC_API_KEY is set), then lm_studio (if LM_STUDIO_BASE_URL is
    # set), then falls back to claude_subscription (the `claude` CLI's own
    # login, no separate credential needed). Set explicitly to pin one.
    llm_backend: str = "auto"  # auto | anthropic_api | lm_studio | claude_subscription
    llm_model: str = "claude-sonnet-5"  # model id for the anthropic_api backend
    # LM Studio's local OpenAI-compatible server -- same env var names as
    # mcp-server/lm_studio_client.py and the enterprise-pain-point-platform
    # pipeline elsewhere in this workspace, for a consistent setup story
    # across projects. Empty chat model = auto-pick the first loaded
    # non-embedding model.
    lm_studio_base_url: str = ""  # e.g. http://localhost:1234/v1
    lm_studio_chat_model: str = ""


settings = Settings()
