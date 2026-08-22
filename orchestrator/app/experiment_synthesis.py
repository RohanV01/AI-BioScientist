"""Two-step synthesis for /experiment conclude (Experiments plan, Phase 3).

The master agent's own per-message SYNTHESIZE step (claude_runner.py) reasons
over whatever raw tool result text is in context for that one turn -- useful
for an immediate answer, but not an audit trail: you can't later point at
*which* structured findings a conclusion actually weighed. This module is
deliberately separate: it reasons only over the structured findings
app/tools/literature_discovery.py's read_paper already extracted and
persisted (data/Experiments/<id>/findings/*.json) across the whole
experiment's lifetime, not raw tool text from one turn. Triggered
explicitly (/experiment conclude), never automatically -- the researcher
decides when an experiment is actually concluded.
"""
import json
from pathlib import Path

import anthropic

from app.config import settings

_SYNTHESIS_MODEL = "claude-sonnet-5"

_CONCLUSION_PROMPT = """\
You are synthesizing a final conclusion for a research experiment from \
structured findings already extracted from each paper it examined. Reason \
ONLY over the findings below -- every claim in your conclusion must trace \
back to a specific paper's claim/support in this evidence set. Note any \
contradictions between papers explicitly rather than silently picking a side.

Return ONLY a JSON object (no markdown fences, no commentary) with exactly \
this shape:

{{
  "conclusion": "the overall synthesized conclusion, in prose",
  "supported_claims": [
    {{"claim": "...", "source_dois": ["10.xxxx/..."], "confidence": "high|medium|low"}}
  ],
  "contradictions": [
    {{"description": "...", "source_dois": ["10.xxxx/...", "10.yyyy/..."]}}
  ]
}}

If the evidence is too thin or too narrow to conclude anything meaningful, \
say so plainly in "conclusion" rather than overreaching.

Structured findings (one entry per paper read in this experiment):
{findings}
"""


def _parse_json_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def load_all_findings(findings_dir: Path) -> list[dict]:
    if not findings_dir.is_dir():
        return []
    findings = []
    for path in sorted(findings_dir.glob("*.json")):
        findings.append(json.loads(path.read_text()))
    return findings


async def synthesize_conclusion(findings: list[dict]) -> dict:
    """`findings` is read_paper's persisted output, one dict per paper (each
    stamped with its own "doi"). Returns {conclusion, supported_claims,
    contradictions} -- see _CONCLUSION_PROMPT for the exact shape. Raises
    anthropic.APIError / json.JSONDecodeError on failure; the caller decides
    how to report that.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=_SYNTHESIS_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": _CONCLUSION_PROMPT.format(findings=json.dumps(findings, indent=2))}],
    )
    raw = "".join(block.text for block in resp.content if hasattr(block, "text"))
    return _parse_json_response(raw)


def format_conclusion_markdown(conclusion: dict) -> str:
    lines = ["# Experiment Conclusion", "", conclusion.get("conclusion", "")]
    claims = conclusion.get("supported_claims", [])
    if claims:
        lines += ["", "## Supported claims", ""]
        for c in claims:
            dois = ", ".join(c.get("source_dois", []))
            lines.append(f"- **{c.get('claim', '')}** (confidence: {c.get('confidence', '')}) -- {dois}")
    contradictions = conclusion.get("contradictions", [])
    if contradictions:
        lines += ["", "## Contradictions between papers", ""]
        for c in contradictions:
            dois = ", ".join(c.get("source_dois", []))
            lines.append(f"- {c.get('description', '')} -- {dois}")
    return "\n".join(lines)
