"""Async OpenAI-compatible client wired to OnlySq with retries and JSON-mode helper."""
from __future__ import annotations

import asyncio
from typing import Any

import orjson
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError

from azura.config import get_settings
from azura.utils.log import get_logger

log = get_logger("llm.client")

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Return a cached AsyncOpenAI bound to the OnlySq base url."""
    global _client
    if _client is not None:
        return _client
    s = get_settings()
    if not s.onlysq_api_key:
        log.warning("ONLYSQ_API_KEY is empty — requests will fail until you set it")
    _client = AsyncOpenAI(api_key=s.onlysq_api_key or "missing", base_url=s.onlysq_base_url)
    return _client


async def _with_retries(fn, *, attempts: int = 4, base_delay: float = 1.0):
    """Run an async callable with exponential backoff over transient errors."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await fn()
        except (RateLimitError, APIConnectionError) as e:
            last = e
            delay = base_delay * (2**i)
            log.warning("llm transient {} attempt {}/{}, sleep {:.1f}s", type(e).__name__, i + 1, attempts, delay)
            await asyncio.sleep(delay)
        except APIError as e:
            last = e
            if 500 <= getattr(e, "status_code", 500) < 600:
                delay = base_delay * (2**i)
                log.warning("llm 5xx attempt {}/{}, sleep {:.1f}s", i + 1, attempts, delay)
                await asyncio.sleep(delay)
                continue
            raise
    assert last is not None
    raise last


async def chat(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.8,
    top_p: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
    response_format: dict | None = None,
) -> Any:
    """Plain chat-completions call returning the raw OpenAI response object."""
    cli = get_client()

    async def call():
        kw: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if top_p is not None:
            kw["top_p"] = top_p
        if max_tokens is not None:
            kw["max_tokens"] = max_tokens
        if tools:
            kw["tools"] = tools
            if tool_choice is not None:
                kw["tool_choice"] = tool_choice
        if response_format is not None:
            kw["response_format"] = response_format
        return await cli.chat.completions.create(**kw)

    return await _with_retries(call)


async def chat_text(*, model: str, messages: list[dict[str, Any]], **kw) -> str:
    """Convenience: return content of the first choice."""
    r = await chat(model=model, messages=messages, **kw)
    return r.choices[0].message.content or ""


async def chat_json(*, model: str, messages: list[dict[str, Any]], **kw) -> dict:
    """Convenience: parse JSON object out of the model output, tolerant to code fences."""
    raw = await chat_text(model=model, messages=messages, **kw)
    return _extract_json(raw)


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction; falls back to first {...} block."""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    try:
        return orjson.loads(s)
    except Exception:
        i = s.find("{")
        j = s.rfind("}")
        if i >= 0 and j > i:
            return orjson.loads(s[i : j + 1])
        raise


async def embed(*, model: str, inputs: list[str]) -> list[list[float]]:
    """Embeddings via OpenAI-compatible /embeddings."""
    cli = get_client()

    async def call():
        return await cli.embeddings.create(model=model, input=inputs)

    r = await _with_retries(call)
    return [d.embedding for d in r.data]
