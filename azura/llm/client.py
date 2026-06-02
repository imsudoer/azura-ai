"""Async OpenAI-compatible client wired to OnlySq with retries and JSON-mode helper."""
from __future__ import annotations

import asyncio
from typing import Any

import orjson
from openai import APIConnectionError, APIError, APIStatusError, AsyncOpenAI, RateLimitError

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
        except (APIStatusError, APIError) as e:
            last = e
            sc = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", 0)
            if sc and 500 <= sc < 600:
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
    """Convenience: parse JSON object out of the model output, tolerant to code fences.

    We never forward `response_format` to the upstream: many OnlySq-routed models
    (incl. pplx-gemini-3.1-pro) reject it with HTTP 500. `_extract_json` is
    robust enough to handle plain prose with a JSON block inside.
    """
    kw.pop("response_format", None)
    raw = await chat_text(model=model, messages=messages, **kw)
    try:
        return _extract_json(raw)
    except Exception as e:
        log.error(
            "JSON parse failed ({}). model={} raw_len={}\n--- RAW ---\n{}\n--- END ---",
            e, model, len(raw), raw[:8000],
        )
        raise


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction from a model response.

    Strategy:
      1. Strip code fences.
      2. Try plain orjson.loads().
      3. Try the outer {...} block.
      4. If still truncated, repair by closing dangling strings, arrays, objects.
    """
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    try:
        return orjson.loads(s)
    except Exception:
        pass
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        try:
            return orjson.loads(s[i : j + 1])
        except Exception:
            pass
    if i >= 0:
        repaired = _repair_truncated_json(s[i:])
        if repaired is not None:
            return repaired
    raise ValueError("could not parse JSON from model response")


def _repair_truncated_json(s: str) -> dict | None:
    """Attempt to close dangling strings / arrays / objects in a truncated JSON.

    Walks the text tracking string state, escape state, and a stack of open braces
    / brackets. At end, closes whatever is still open and tries to parse.
    """
    out = []
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        out.append(ch)
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
    if in_str:
        out.append('"')
    last_real = ""
    for ch in reversed(out):
        if not ch.isspace():
            last_real = ch
            break
    if last_real == ",":
        for idx in range(len(out) - 1, -1, -1):
            if out[idx] == ",":
                out[idx] = " "
                break
            if not out[idx].isspace():
                break
    while stack:
        out.append(stack.pop())
    candidate = "".join(out)
    try:
        return orjson.loads(candidate)
    except Exception:
        return None


async def embed(*, model: str, inputs: list[str]) -> list[list[float]]:
    """Embeddings via OpenAI-compatible /embeddings."""
    cli = get_client()

    async def call():
        return await cli.embeddings.create(model=model, input=inputs)

    r = await _with_retries(call)
    return [d.embedding for d in r.data]
