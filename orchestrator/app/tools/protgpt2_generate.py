"""A real ProtGPT2 MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1.5, local-GPU tools) -- real local inference via the
`transformers` library against `nferruz/ProtGPT2` (a real, published
protein language model, GPT2 architecture, 738M params, trained on
UniRef50). Confirmed live in an earlier session that this specific
model has no HF hosted Inference Provider available (its
`inferenceProviderMapping` is empty, unlike ESM2 -- see
`app/tools/huggingface.py`'s own remote-API tool) -- local inference is
the only path, which is exactly what needing a GPU passed through to
this container (Phase 1.5's whole premise) is for.

Distinct from `huggingface.py`'s ESM2 tool (masked-residue prediction
on an existing sequence) and AbLang (antibody-specific restoration):
this is unconditional/general de novo sequence generation -- write a
new, plausible protein from scratch (or continuing a given prefix),
not fill in or fix an existing one.

Uses the GPU automatically when available (torch ships CUDA support by
default from PyPI, confirmed live -- see docker-compose.gpu.yml), falls
back to CPU otherwise -- correctly slower (a real, noticeably longer
wait for a 738M-parameter model), not broken.
"""
import asyncio
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MODEL_NAME = "nferruz/ProtGPT2"
MAX_SEQUENCES = 5
MAX_LENGTH_TOKENS = 400  # ~4 residues/token on average per the model's own README

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        import torch
        from transformers import pipeline

        device = 0 if torch.cuda.is_available() else -1
        _pipeline = pipeline("text-generation", model=MODEL_NAME, device=device)
    return _pipeline


def _generate(prefix: str, max_length: int, num_sequences: int) -> list[dict]:
    protgpt2 = _get_pipeline()
    # Real documented defaults from the model's own README (top_k=950,
    # repetition_penalty=1.2) -- not guessed. max_new_tokens, not
    # max_length: confirmed live that transformers' pipeline defaults
    # max_new_tokens=256 and lets it silently take precedence over
    # max_length when both are present (a real, live-caught bug this
    # tool had before this fix -- the caller's requested length was
    # being ignored).
    results = protgpt2(
        prefix, max_new_tokens=max_length, do_sample=True, top_k=950,
        repetition_penalty=1.2, num_return_sequences=num_sequences, eos_token_id=0,
    )
    return results


@tool(
    "generate_protein_sequence",
    "Generate real de novo protein sequence(s) via ProtGPT2 (a "
    "published 738M-parameter protein language model trained on "
    "UniRef50). Optionally continue from a given amino-acid prefix "
    "(leave empty to let the model choose its own start). "
    "max_length_tokens controls output length (roughly 4 residues per "
    "token). Genuinely slow on CPU (minutes) if no GPU is available to "
    "this container -- do not abandon a call early on this basis "
    "alone. Never state a generated sequence this tool didn't actually "
    "produce.",
    {"prefix": str, "max_length_tokens": int, "num_sequences": int},
)
async def generate_protein_sequence(args: dict[str, Any]) -> dict[str, Any]:
    prefix = (args.get("prefix") or "").strip().upper()
    max_length = args.get("max_length_tokens", 100)
    num_sequences = args.get("num_sequences", 1)
    valid_aa = set("ACDEFGHIKLMNPQRSTVWY")
    if prefix and not set(prefix) <= valid_aa:
        return {"content": [{"type": "text", "text": "prefix must contain only standard amino acid letters, or be empty."}]}
    if not isinstance(max_length, int) or not (10 <= max_length <= MAX_LENGTH_TOKENS):
        return {"content": [{"type": "text", "text": f"max_length_tokens must be an integer between 10 and {MAX_LENGTH_TOKENS}."}]}
    if not isinstance(num_sequences, int) or not (1 <= num_sequences <= MAX_SEQUENCES):
        return {"content": [{"type": "text", "text": f"num_sequences must be an integer between 1 and {MAX_SEQUENCES}."}]}

    prompt = prefix if prefix else "<|endoftext|>"

    try:
        results = await asyncio.to_thread(_generate, prompt, max_length, num_sequences)
    except Exception as exc:  # noqa: BLE001 -- surface real transformers/model errors to the caller
        return {"content": [{"type": "text", "text": f"ProtGPT2 generation failed: {exc}"}]}

    lines = [f"ProtGPT2 de novo protein generation [protgpt2:sequence] -- {len(results)} sequence(s):"]
    for i, r in enumerate(results):
        # Confirmed live: with an empty prefix the model echoes the
        # literal "<|endoftext|>" start token verbatim at the front of
        # its own output -- stripped here, not part of the sequence.
        sequence = r["generated_text"].replace("\n", "").removeprefix("<|endoftext|>")
        lines.append(f"- sequence {i + 1}: {sequence}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_protgpt2_generate_mcp_server():
    return create_sdk_mcp_server(name="protgpt2_generate", tools=[generate_protein_sequence])
