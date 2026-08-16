"""A real Hugging Face MCP tool (docs/10-build-plan.md Phase 5 -- the
research report's Section 10 finding: HF hosts bio-specific models (ESM,
ProtBert, DNABERT, ChemBERTa-class) that can answer some "needs compute"
Tier-3 experiments without any new procurement, via HF's Inference API
rather than local GPU infrastructure).

BYO-credential tool source (requires_credential=True) -- unlike every
other tool source so far, this needs a real API token (free to create,
but not anonymous the way NCBI/EBI/RCSB's public APIs are). Per product
decision 2026-08-16: wired through the existing Credential Vault
(app/vault.py, scripts/add_credential.py), not hardcoded to any one
person's key -- any org can bring their own HF token.

One tool: masked-residue prediction on a protein sequence via ESM2 (a
protein language model) -- given a sequence with a masked position,
returns the model's ranked amino-acid predictions with probabilities.
This is directly interpretable, citable model output (unlike raw
embeddings, which aren't something you can paste into a grounded
answer) and supports a real research pattern: comparing a wild-type
residue's predicted likelihood against a candidate mutation's, as a
cheap first-pass mutation-effect signal, without running a full fold.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

HF_ROUTER_URL = "https://router.huggingface.co/hf-inference/models"
ESM2_MODEL = "facebook/esm2_t12_35M_UR50D"


def build_huggingface_mcp_server(api_key: str):
    headers = {"Authorization": f"Bearer {api_key}"}

    @tool(
        "predict_masked_residue",
        "Given a protein sequence with exactly one position replaced by "
        "'<mask>', return the ESM2 protein language model's top predicted "
        "amino acids for that position with probabilities -- a cheap "
        "signal for how well-tolerated a residue is at that position "
        "(compare the wild-type residue's rank/probability against a "
        "candidate mutation's). Never state a probability this tool "
        "didn't return.",
        {"masked_sequence": str, "top_k": int},
    )
    async def predict_masked_residue(args: dict[str, Any]) -> dict[str, Any]:
        sequence = args["masked_sequence"]
        if "<mask>" not in sequence:
            return {
                "content": [
                    {"type": "text", "text": "masked_sequence must contain exactly one '<mask>' token marking the position to predict."}
                ]
            }
        top_k = min(int(args.get("top_k", 5)), 20)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{HF_ROUTER_URL}/{ESM2_MODEL}",
                headers=headers,
                json={"inputs": sequence, "parameters": {"top_k": top_k}},
            )
            if resp.status_code == 401:
                return {"content": [{"type": "text", "text": "Hugging Face API token was rejected (401) -- check the configured credential."}]}
            resp.raise_for_status()
            predictions = resp.json()

        if not isinstance(predictions, list) or not predictions:
            return {"content": [{"type": "text", "text": f"No predictions returned for this sequence: {predictions!r}"}]}

        # [ESM2:model-id] is the citable unit here, not an external
        # database record -- there's no record ID to look up, this is
        # live model inference, so what's citable is which model
        # produced the prediction (a methodological citation, matched by
        # claude_runner.py's RECORD_REF_PATTERNS same as everything
        # else, just citing a method/model rather than a database entry).
        lines = [f"ESM2 predictions at the masked position [ESM2:{ESM2_MODEL}]:"]
        for p in predictions[:top_k]:
            lines.append(f"- {p.get('token_str', '?')}: probability {p.get('score', 0):.4f}")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    return create_sdk_mcp_server(name="huggingface", tools=[predict_masked_residue])
