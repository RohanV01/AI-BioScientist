"""OpenAI adapter — uses response_format=json_schema for structured output."""
from __future__ import annotations
import json
from typing import Optional, Type
from pydantic import BaseModel

from .provider import LLMCapabilities, LLMProvider, LLMResult


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self.model = model
        self.capabilities = LLMCapabilities(
            context_tokens=128_000,
            supports_json_mode=True,
            cost_per_1k_input=0.005,
            cost_per_1k_output=0.015,
            quality_tier="frontier",
            strips_thinking_tags=False,
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
        messages.append({"role": "user", "content": prompt})

        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            }

        resp = self._client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        parsed_dict = json.loads(text) if schema else None

        usage = resp.usage
        input_tok = usage.prompt_tokens
        output_tok = usage.completion_tokens
        cost = (input_tok / 1000) * self.capabilities.cost_per_1k_input + \
               (output_tok / 1000) * self.capabilities.cost_per_1k_output

        return LLMResult(
            text=text,
            parsed=parsed_dict,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost,
        )
