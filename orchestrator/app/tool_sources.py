"""Get-or-create helpers for TOOL_SOURCE rows (docs/06-data-model.md). Kept
tiny and explicit rather than a generic registry -- there are only a
handful of these at Phase 1, and a registry abstraction isn't earning its
keep yet for one row."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ToolSource


async def get_or_create_pubmed_tool_source(db: AsyncSession) -> ToolSource:
    result = await db.execute(select(ToolSource).where(ToolSource.name == "pubmed"))
    source = result.scalar_one_or_none()
    if source is None:
        source = ToolSource(
            name="pubmed",
            category="literature",
            access_model="free_public",
            requires_credential=False,
            mcp_server_ref="in-process:app.tools.pubmed",
        )
        db.add(source)
        await db.flush()
    return source
