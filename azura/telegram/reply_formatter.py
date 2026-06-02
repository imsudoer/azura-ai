"""Build the agent user_prompt out of the incoming Message + memory context."""
from __future__ import annotations

import orjson

from azura.memory.service import MemoryService
from azura.mind.triggers import TriggerHit


async def build_user_prompt(
    *,
    memory: MemoryService,
    chat_id: int,
    from_user_id: int | None,
    text: str,
    trigger: TriggerHit,
    in_private: bool,
    reply_to_text: str | None = None,
) -> str:
    """Compose a JSON situation block + the actual message text for the agent."""
    about = (
        await memory.recall_about_user(from_user_id, query=text)
        if from_user_id is not None else {}
    )
    chat_ctx = await memory.recall_chat(chat_id, limit_short=20, limit_long=8)
    payload = {
        "chat": {
            "id": chat_id,
            "in_private": in_private,
            "opinion": chat_ctx.get("opinion"),
            "feelings": chat_ctx.get("feelings"),
            "recent_short_memory": chat_ctx.get("short", [])[-12:],
            "stable_facts": chat_ctx.get("long", [])[:8],
        },
        "user": about,
        "trigger": {
            "name_called": trigger.name_called,
            "username_mentioned": trigger.username_mentioned,
            "reply_to_self": trigger.reply_to_self,
            "keyword": trigger.keyword,
            "boundary_hit": trigger.boundary_hit,
        },
        "incoming": {"text": text, "reply_to": reply_to_text},
    }
    return (
        "SITUATION JSON:\n"
        + orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode()
        + "\n\nReact in character. Output messages only (no JSON, no preamble)."
    )
