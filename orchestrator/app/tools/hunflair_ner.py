"""A real HunFlair2 MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1, Transcriptomics cluster) -- biomedical named-entity recognition
(genes, diseases, chemicals, species, cell lines) on caller-supplied
free text, via the `flair` package's pretrained HunFlair2 tagger. Real
local model inference, no external API call per request (the ~1.9GB
model weights are downloaded once and cached under ~/.flair/models/ on
first load).

Confirmed live before wiring (2026-08-26): `Classifier.load('hunflair')`
(v1) is deprecated in favor of `Classifier.load('hunflair2')`, a single
unified tagger (vs. v1's five separate per-entity-type taggers) with a
richer joint tag set (Chemical/Gene/Disease/Species/CellLine) and higher
confidence scores observed on a real test sentence -- used hunflair2.
Model load takes ~1.5s once cached; first-ever load downloads the model
(large, several-minutes on a slow connection) so this tool loads the
tagger lazily on first call, not at import time, to keep container
startup fast.
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

_TAGGER = None


def _get_tagger():
    global _TAGGER
    if _TAGGER is None:
        from flair.nn import Classifier

        _TAGGER = Classifier.load("hunflair2")
    return _TAGGER


@tool(
    "extract_biomedical_entities",
    "Given free-text biomedical text (e.g. an abstract or a sentence), "
    "run HunFlair2 (flair package) named-entity recognition to extract "
    "genes, diseases, chemicals, species, and cell lines with per-entity "
    "confidence scores. Real local model inference, not a lookup. Never "
    "state an entity or confidence score this tool didn't actually "
    "extract.",
    {"text": str},
)
async def extract_biomedical_entities(args: dict[str, Any]) -> dict[str, Any]:
    text = (args.get("text") or "").strip()
    if not text:
        return {"content": [{"type": "text", "text": "text must not be empty."}]}
    if len(text) > 5000:
        return {"content": [{"type": "text", "text": "text must be at most 5000 characters."}]}

    import asyncio

    def _run():
        from flair.data import Sentence

        sentence = Sentence(text)
        _get_tagger().predict(sentence)
        return sentence.get_labels()

    try:
        labels = await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001 -- surface real flair/model errors to the caller
        return {"content": [{"type": "text", "text": f"HunFlair2 extraction failed: {exc}"}]}

    if not labels:
        return {"content": [{"type": "text", "text": "HunFlair2 [hunflair2:ner] found no biomedical entities in this text."}]}

    lines = [f"HunFlair2 [hunflair2:ner] found {len(labels)} biomedical entity/entities:"]
    for label in labels:
        span = label.data_point
        lines.append(f'- "{span.text}" -> {label.value} (confidence {label.score:.3f})')
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_hunflair_ner_mcp_server():
    return create_sdk_mcp_server(name="hunflair_ner", tools=[extract_biomedical_entities])
