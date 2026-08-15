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


settings = Settings()
