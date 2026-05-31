"""
LM Studio adapter — OpenAI-compatible local server.
Strips <think>…</think> blocks from reasoning models (Qwen3, DeepSeek-R1, etc.).
Structured output uses JSON-mode + re-prompt-on-failure loop.
"""
from __future__ import annotations
import json
import re
from typing import Optional, Type
from pydantic import BaseModel

from .provider import LLMCapabilities, LLMProvider, LLMResult

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> str:
    """Pull JSON from a code fence or the raw text."""
    m = _JSON_FENCE.search(text)
    return m.group(1).strip() if m else text.strip()


class LMStudioProvider(LLMProvider):
    name = "lmstudio"

    def __init__(self, base_url: str, model: str):
        from openai import OpenAI
        self._client = OpenAI(base_url=base_url, api_key="lmstudio")
        self.model = model
        self.capabilities = LLMCapabilities(
            context_tokens=8_192,
            supports_json_mode=False,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
            quality_tier="small",
            strips_thinking_tags=True,
        )

    def complete(
        self,
        prompt: str,
        *,
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        system: str = "",
    ) -> LLMResult:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        if schema is not None:
            schema_hint = json.dumps(schema.model_json_schema(), indent=2)
            prompt = (
                f"{prompt}\n\n"
                f"Respond ONLY with a JSON object matching this schema:\n```json\n{schema_hint}\n```\n"
                "Output no other text."
            )
        messages.append({"role": "user", "content": prompt})

        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw = resp.choices[0].message.content or ""
        text = self._strip_thinking(raw)

        parsed_dict: Optional[dict] = None
        if schema is not None:
            json_str = _extract_json(text)
            try:
                parsed_dict = schema.model_validate_json(json_str).model_dump()
            except Exception:
                # Re-prompt once asking to fix JSON
                fix_msg = [
                    *messages,
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "Your output was not valid JSON. Return ONLY the JSON object."},
                ]
                resp2 = self._client.chat.completions.create(
                    model=self.model,
                    messages=fix_msg,
                    temperature=0.0,
                    max_tokens=max_tokens,
                )
                raw2 = resp2.choices[0].message.content or ""
                text = self._strip_thinking(raw2)
                try:
                    parsed_dict = schema.model_validate_json(_extract_json(text)).model_dump()
                except Exception:
                    parsed_dict = None

        return LLMResult(text=text, parsed=parsed_dict)
