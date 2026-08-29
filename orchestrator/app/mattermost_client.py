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
        if root_id and resp.status_code == 400:
            # A root_id Mattermost rejects (the referenced post was deleted,
            # or -- as hit live during testing -- never existed) must not
            # take down the whole response pipeline; found the hard way
            # when this raised uncaught mid-_run_agent_and_respond and lost
            # the DB commit for an otherwise-successful agent run, not just
            # the threading. Falls back to a top-level post instead.
            payload["root_id"] = ""
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

    async def get_file_info(self, file_id: str) -> dict:
        """Real Mattermost endpoint `GET /api/v4/files/{file_id}/info` --
        confirmed against Mattermost's own server source
        (server/channels/api4/file.go) before relying on it. Returns
        real metadata: name, size, mime_type, extension, etc."""
        resp = await self._client.get(f"/api/v4/files/{file_id}/info")
        resp.raise_for_status()
        return resp.json()

    async def download_file(self, file_id: str) -> bytes:
        """Real Mattermost endpoint `GET /api/v4/files/{file_id}` -- returns
        the raw file bytes directly (confirmed against Mattermost's own
        server source, same file as get_file_info above). Uses a longer
        timeout than the base client's 15s default since real uploaded
        research files (count matrices, FASTQ) can be large."""
        resp = await self._client.get(f"/api/v4/files/{file_id}", timeout=120.0)
        resp.raise_for_status()
        return resp.content

    async def aclose(self) -> None:
        await self._client.aclose()
