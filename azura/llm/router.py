"""Pick the right model per intent: reply (opus) vs think (pplx)."""
from __future__ import annotations

from typing import Literal

from azura.config import get_settings
from azura.llm.client import chat_json, chat_text, embed

Intent = Literal["reply", "think", "summarize", "tag", "decide", "translate", "tool", "persona"]

_FAST: set[Intent] = {"think", "summarize", "tag", "decide", "translate", "tool", "persona"}


def model_for(intent: Intent) -> str:
    """Return the configured model name for a given intent."""
    s = get_settings()
    if intent == "reply":
        return s.model_reply
    if intent in _FAST:
        return s.model_think
    return s.model_think


async def think_text(messages: list[dict], **kw) -> str:
    return await chat_text(model=model_for("think"), messages=messages, **kw)


async def think_json(messages: list[dict], **kw) -> dict:
    return await chat_json(model=model_for("think"), messages=messages, **kw)


async def reply_text(messages: list[dict], **kw) -> str:
    return await chat_text(model=model_for("reply"), messages=messages, **kw)


async def reply_json(messages: list[dict], **kw) -> dict:
    return await chat_json(model=model_for("reply"), messages=messages, **kw)


async def embed_texts(inputs: list[str]) -> list[list[float]]:
    s = get_settings()
    return await embed(model=s.model_embed, inputs=inputs)
