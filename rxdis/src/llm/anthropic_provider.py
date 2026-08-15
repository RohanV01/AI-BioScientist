"""
Anthropic Claude adapter.
Uses prompt caching for long system prompts (DB-context windows).
"""
from __future__ import annotations
import json
from typing import Optional, Type
from pydantic import BaseModel

from .provider import LLMCapabilities, LLMProvider, LLMResult


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        import anthropic as _anthropic
        self._client = _anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.capabilities = LLMCapabilities(
            context_tokens=200_000,
            supports_json_mode=True,
            cost_per_1k_input=0.003,
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
        messages = [{"role": "user", "content": prompt}]

        if schema is not None:
            # Use tool-use for structured output — most reliable on Claude
            tool_def = {
                "name": "structured_output",
                "description": "Return your answer in this exact JSON schema.",
                "input_schema": schema.model_json_schema(),
            }
            kwargs = dict(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=[tool_def],
                tool_choice={"type": "tool", "name": "structured_output"},
                messages=messages,
            )
            if system:
                kwargs["system"] = [
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                ]
            resp = self._client.messages.create(**kwargs)
            # Extract tool input block
            tool_block = next(
                b for b in resp.content if b.type == "tool_use"
            )
            parsed_dict = tool_block.input
            text = json.dumps(parsed_dict)
        else:
            kwargs = dict(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,
            )
            if system:
                kwargs["system"] = [
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                ]
            resp = self._client.messages.create(**kwargs)
            text = resp.content[0].text
            parsed_dict = None

        usage = resp.usage
        input_tok = usage.input_tokens
        output_tok = usage.output_tokens
        cost = (input_tok / 1000) * self.capabilities.cost_per_1k_input + \
               (output_tok / 1000) * self.capabilities.cost_per_1k_output

        return LLMResult(
            text=text,
            parsed=parsed_dict,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost,
        )
