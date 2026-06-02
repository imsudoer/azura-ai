"""Media analysis tools: image/voice description (placeholders + delegating to sender)."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Media tools (descriptions saved to memory)."""

    async def note_media(args: dict) -> dict:
        text = f"saw media: kind={args.get('kind')} desc={args.get('description')}"
        await ctx.memory.short.add(
            int(args.get("chat_id") or ctx.chat_id or 0),
            text,
            topic="media",
            user_id=args.get("user_id"),
            importance=0.4,
        )
        return {"ok": True}

    return [
        make_spec("note_media",
                  "Remember a piece of media you saw with a short description.",
                  {"type": "object", "required": ["kind", "description"], "properties": {
                      "kind": {"type": "string"},
                      "description": {"type": "string"},
                      "chat_id": {"type": "integer"},
                      "user_id": {"type": "integer"}}},
                  note_media),
    ]
