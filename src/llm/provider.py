"""
Provider-agnostic LLM interface.
Every phase calls provider.complete() — never a vendor SDK directly.
"""
from __future__ import annotations
import re
from typing import Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMCapabilities(BaseModel):
    context_tokens: int
    supports_json_mode: bool
    cost_per_1k_input: float
    cost_per_1k_output: float
    quality_tier: str      # "frontier" | "mid" | "small"
    strips_thinking_tags: bool


class LLMResult(BaseModel):
    text: str
    parsed: Optional[dict] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class LLMProvider:
    """Base class — subclasses implement _call()."""
    name: str = "base"
    model: str = ""
    capabilities: LLMCapabilities

    def complete(
        self,
        prompt: str,
        *,
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        system: str = "",
    ) -> LLMResult:
        raise NotImplementedError

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove <think>…</think> blocks emitted by local reasoning models."""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    def chunk_size(self) -> int:
        """Items per map-reduce chunk, scaled to context window."""
        ctx = self.capabilities.context_tokens
        if ctx < 16_000:
            return 8
        if ctx < 64_000:
            return 30
        return 80

    def reduce_mode(self) -> str:
        """'tree' for small local models, 'single_pass' for frontier."""
        return "single_pass" if self.capabilities.context_tokens >= 100_000 else "tree"

    def self_consistency_rounds(self, critical: bool = False) -> int:
        """Number of independent completions to run for critical gates."""
        if self.capabilities.quality_tier == "small" and critical:
            return 2
        return 1
