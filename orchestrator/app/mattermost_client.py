"""Thin wrapper over the Mattermost REST API the Orchestrator needs:
posting responses back as a given bot. Not a general-purpose Mattermost
SDK -- just what docs/07-system-architecture.md's Message Router and
Grounding Layer actually call."""
import httpx

from app.config import settings


class MattermostClient:
    def __init__(self, bot_token: str):
        self._client = httpx.AsyncClient(
            base_url=settings.mattermost_url,
            headers={"Authorization": f"Bearer {bot_token}"},
            timeout=15.0,
        )

    async def post_message(
        self, channel_id: str, message: str, root_id: str = "", attachments: list[dict] | None = None
    ) -> dict:
        payload: dict = {"channel_id": channel_id, "message": message, "root_id": root_id}
        if attachments:
            payload["props"] = {"attachments": attachments}
        resp = await self._client.post("/api/v4/posts", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def add_reaction(self, user_id: str, post_id: str, emoji_name: str) -> dict:
        resp = await self._client.post(
            "/api/v4/reactions",
            json={"user_id": user_id, "post_id": post_id, "emoji_name": emoji_name},
        )
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()
