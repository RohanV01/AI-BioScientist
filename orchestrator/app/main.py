from fastapi import FastAPI

from app.routers import mattermost_webhook, prediction_outcomes, reports

app = FastAPI(
    title="OpenBioLab Orchestrator",
    description="Routes Mattermost messages to Claude Code/Codex agents; enforces grounding on every response.",
    version="0.1.0",
)

app.include_router(mattermost_webhook.router)
app.include_router(reports.router)
app.include_router(prediction_outcomes.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
