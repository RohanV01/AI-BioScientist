"""Modular one-shot text-completion backend for read_paper's structured
extraction and /experiment conclude's synthesis (app/experiment_synthesis.py)
-- distinct from the master agent's own multi-turn Plan/Execute/Synthesize
loop (app/claude_runner.py), which always drives the `claude` CLI as a
subprocess via claude_agent_sdk regardless of this module.

Three interchangeable backends, selected by LLM_BACKEND in .env (default
"auto"):

  - anthropic_api: direct Messages API call. Needs ANTHROPIC_API_KEY.
  - lm_studio: local OpenAI-compatible server (LM_STUDIO_BASE_URL, same env
    var convention as mcp-server/lm_studio_client.py and the
    enterprise-pain-point-platform pipeline elsewhere in this workspace) --
    free, fully offline, whatever model is currently loaded there.
  - claude_subscription: claude_agent_sdk's query() in a bare, single-turn,
    no-tools mode -- reuses whatever `claude` CLI login already exists on
    this machine (subscription-billed, not API-key billed), so it needs no
    separate credential in .env at all.

"auto" tries anthropic_api first (if ANTHROPIC_API_KEY is set), then
lm_studio (if LM_STUDIO_BASE_URL is set), then falls back to
claude_subscription, which is always considered available since it rides
on the CLI's own login rather than a config value here -- the call itself
fails loudly if that login doesn't exist.
"""
from app.config import settings


class LLMBackendError(Exception):
    pass


async def _complete_anthropic_api(prompt: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        resp = await client.messages.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        raise LLMBackendError(f"anthropic_api backend failed: {exc}") from exc
    return "".join(block.text for block in resp.content if hasattr(block, "text"))


async def _complete_claude_subscription(prompt: str, max_tokens: int) -> str:
    # Imported lazily -- claude_agent_sdk spawns the `claude` CLI as a
    # subprocess, no reason to pay that import cost for backends that don't
    # use it.
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

    options = ClaudeAgentOptions(
        system_prompt="Respond with exactly what is asked for -- no preamble, no follow-up questions.",
        tools=[],
        mcp_servers={},
        allowed_tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        permission_mode="bypassPermissions",
        max_turns=1,
    )
    parts: list[str] = []
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
    except Exception as exc:
        raise LLMBackendError(f"claude_subscription backend failed: {exc}") from exc
    if not parts:
        raise LLMBackendError("claude_subscription backend returned no text -- is `claude` logged in on this machine?")
    return "\n".join(parts)


async def _complete_lm_studio(prompt: str, max_tokens: int) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            models_resp = await client.get(f"{settings.lm_studio_base_url}/models")
            models_resp.raise_for_status()
            models = [m["id"] for m in models_resp.json().get("data", [])]
            if not models:
                raise LLMBackendError("no models loaded in LM Studio")
            model = settings.lm_studio_chat_model or next(
                (m for m in models if "embed" not in m.lower()), None
            )
            if model is None:
                raise LLMBackendError("no chat-capable model loaded in LM Studio (only embedding models found)")

            resp = await client.post(
                f"{settings.lm_studio_base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    # Local "thinking" models can burn most of max_tokens on
                    # hidden reasoning before ever emitting the actual
                    # answer -- same padding precedent as
                    # mcp-server/lm_studio_client.py's chat().
                    "max_tokens": max(max_tokens, 512) + 2048,
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMBackendError(f"lm_studio backend failed: {exc}") from exc
        return resp.json()["choices"][0]["message"]["content"]


_BACKENDS = {
    "anthropic_api": _complete_anthropic_api,
    "lm_studio": _complete_lm_studio,
    "claude_subscription": _complete_claude_subscription,
}

# Order "auto" tries backends in -- cheapest-to-verify-as-configured and
# most predictable (a real API key) first, free/local next, CLI subprocess
# last since it's the heaviest per-call.
_AUTO_ORDER = ["anthropic_api", "lm_studio", "claude_subscription"]


def _is_configured(name: str) -> bool:
    if name == "anthropic_api":
        return bool(settings.anthropic_api_key)
    if name == "lm_studio":
        return bool(settings.lm_studio_base_url)
    if name == "claude_subscription":
        return True  # rides on the CLI's own login, not a value in .env
    return False


async def complete(prompt: str, max_tokens: int = 2000) -> str:
    """One one-shot text completion via whichever backend is configured
    (settings.llm_backend). Raises LLMBackendError -- with every attempted
    backend's own failure reason, in "auto" mode -- if nothing succeeded.
    """
    backend = settings.llm_backend
    if backend != "auto":
        fn = _BACKENDS.get(backend)
        if fn is None:
            raise LLMBackendError(
                f"Unknown LLM_BACKEND {backend!r} -- must be one of {list(_BACKENDS)} or 'auto'."
            )
        return await fn(prompt, max_tokens)

    errors = []
    for name in _AUTO_ORDER:
        if not _is_configured(name):
            continue
        try:
            return await _BACKENDS[name](prompt, max_tokens)
        except LLMBackendError as exc:
            errors.append(str(exc))

    if not errors:
        raise LLMBackendError(
            "No LLM backend is usable -- set ANTHROPIC_API_KEY, LM_STUDIO_BASE_URL, "
            "or make sure `claude` is logged in on this machine."
        )
    raise LLMBackendError("Every configured LLM backend failed: " + "; ".join(errors))
