"""Chat-level tools: mute, importance, set chat opinion bias."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Chat management tools."""

    async def mute_chat(args: dict) -> dict:
        cid = int(args["chat_id"])
        await ctx.memory.repos.chats.set_muted(cid, True)
        await ctx.memory.repos.journal.write(
            f"muted chat {cid} ({args.get('reason') or 'no reason'})", kind="action", chat_id=cid
        )
        return {"ok": True}

    async def unmute_chat(args: dict) -> dict:
        cid = int(args["chat_id"])
        await ctx.memory.repos.chats.set_muted(cid, False)
        await ctx.memory.repos.journal.write(f"unmuted chat {cid}", kind="action", chat_id=cid)
        return {"ok": True}

    async def set_importance(args: dict) -> dict:
        await ctx.memory.repos.chats.set_importance(int(args["chat_id"]), int(args["value"]))
        return {"ok": True}

    return [
        make_spec("mute_chat",
                  "Mute a chat. It moves to the low-priority tier.",
                  {"type": "object", "required": ["chat_id"], "properties": {
                      "chat_id": {"type": "integer"}, "reason": {"type": "string"}}},
                  mute_chat),
        make_spec("unmute_chat",
                  "Unmute a chat.",
                  {"type": "object", "required": ["chat_id"], "properties": {
                      "chat_id": {"type": "integer"}}},
                  unmute_chat),
        make_spec("set_chat_importance",
                  "Set chat importance integer (higher = checked sooner).",
                  {"type": "object", "required": ["chat_id", "value"], "properties": {
                      "chat_id": {"type": "integer"}, "value": {"type": "integer"}}},
                  set_importance),
    ]
