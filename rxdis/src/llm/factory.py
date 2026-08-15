"""Build the active LLMProvider from a RunConfig + env vars."""
from __future__ import annotations
from src.config.run_config import LLMConfig
from src.config import settings
from .provider import LLMProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .lmstudio_provider import LMStudioProvider


def make_provider(cfg: LLMConfig) -> LLMProvider:
    if cfg.provider == "anthropic":
        key = _resolve_key(cfg.anthropic.api_key_ref, settings.ANTHROPIC_API_KEY)
        return AnthropicProvider(api_key=key, model=cfg.anthropic.model)

    if cfg.provider == "openai":
        key = _resolve_key(cfg.openai.api_key_ref, settings.OPENAI_API_KEY)
        return OpenAIProvider(api_key=key, model=cfg.openai.model)

    # lmstudio (default)
    base_url = cfg.lmstudio.base_url or settings.LMSTUDIO_BASE_URL
    model = cfg.lmstudio.model or settings.LMSTUDIO_MODEL
    return LMStudioProvider(base_url=base_url, model=model)


def _resolve_key(ref: str | None, env_fallback: str) -> str:
    """
    If ref starts with 'secret://', look it up from the DB (future).
    Otherwise treat it as a literal key or fall back to env.
    """
    if ref and not ref.startswith("secret://"):
        return ref
    return env_fallback
