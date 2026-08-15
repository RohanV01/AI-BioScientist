"""Structured output rendering (docs/05-ux-behavior.md Section 3): short
output renders directly as a Mattermost attachment; larger structured
output (a multi-tool synthesis with a big table) gets a short summary
in the attachment plus a link-out to the full report, rather than
dumping a long raw markdown table into chat -- markdown tables degrade
badly on mobile and in narrow channel widths.

No "canvas view" at MVP (post-MVP per the UX doc) -- the link-out is to
a plain rendered markdown file the Orchestrator Service serves itself,
via app/routers/reports.py.
"""
import re

# A markdown table row: "| ... | ... |". Excludes the header-separator
# row ("|---|---|") since that's formatting, not a data row.
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

MAX_INLINE_ROWS = 5
SUMMARY_CHAR_LIMIT = 600


def _table_data_row_count(body: str) -> int:
    return sum(
        1
        for line in body.splitlines()
        if _TABLE_ROW_RE.match(line) and not _TABLE_SEPARATOR_RE.match(line)
    )


def build_response_attachment(body: str, report_url: str, color: str | None = None) -> dict:
    """One Mattermost attachment dict for a response body. Renders the
    full body if it's short (no table, or a table with <= MAX_INLINE_ROWS
    data rows including its header row); otherwise truncates to a summary
    with a link to the full report at report_url."""
    attachment: dict = {}
    if color:
        attachment["color"] = color

    if _table_data_row_count(body) <= MAX_INLINE_ROWS:
        attachment["text"] = body
        return attachment

    summary = body[:SUMMARY_CHAR_LIMIT].rstrip()
    attachment["text"] = f"{summary}...\n\n📄 [Full report]({report_url})"
    return attachment
