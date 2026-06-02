"""Send-content tools: text bursts, stickers, gifs, photos by URL, tails."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Outbound message tools."""

    async def send_messages(args: dict) -> dict:
        if ctx.sender is None:
            return {"error": "sender not bound"}
        cid = int(args.get("chat_id") or ctx.chat_id or 0)
        msgs = [str(x) for x in (args.get("messages") or []) if str(x).strip()]
        if not msgs or not cid:
            return {"error": "empty messages or chat"}
        opts = {
            "reply_to": args.get("reply_to"),
            "split": bool(args.get("split", True)),
            "typing": bool(args.get("typing", True)),
        }
        return await ctx.sender(cid, msgs, opts)

    async def send_sticker(args: dict) -> dict:
        if ctx.sticker_sender is None:
            return {"error": "sticker sender not bound"}
        cid = int(args.get("chat_id") or ctx.chat_id or 0)
        return await ctx.sticker_sender(cid, str(args.get("query") or args.get("mood", "")))

    async def send_gif(args: dict) -> dict:
        if ctx.gif_sender is None:
            return {"error": "gif sender not bound"}
        cid = int(args.get("chat_id") or ctx.chat_id or 0)
        return await ctx.gif_sender(cid, str(args["query"]))

    async def send_media(args: dict) -> dict:
        if ctx.media_sender is None:
            return {"error": "media sender not bound"}
        cid = int(args.get("chat_id") or ctx.chat_id or 0)
        return await ctx.media_sender(cid, str(args["url"]), str(args.get("kind", "auto")))

    async def schedule_tail(args: dict) -> dict:
        cid = int(args.get("chat_id") or ctx.chat_id or 0)
        delay_min = float(args.get("delay_min_s", 10 * 60))
        delay_max = float(args.get("delay_max_s", 40 * 60))
        item = ctx.tails.schedule(cid, str(args["text"]), delay_min, delay_max)
        return {"due_ts": item.due_ts}

    return [
        make_spec("send_messages",
                  "Send 1..N short messages to a chat. Use this for replies and free-form text.",
                  {"type": "object", "required": ["messages"], "properties": {
                      "chat_id": {"type": "integer"},
                      "messages": {"type": "array", "items": {"type": "string"}},
                      "reply_to": {"type": "integer"},
                      "split": {"type": "boolean"},
                      "typing": {"type": "boolean"}}},
                  send_messages),
        make_spec("send_sticker",
                  "Send a sticker matching a free-form mood/topic query, picked from your own collection.",
                  {"type": "object", "properties": {
                      "chat_id": {"type": "integer"},
                      "query": {"type": "string"},
                      "mood": {"type": "string"}}},
                  send_sticker),
        make_spec("send_gif",
                  "Send a GIF matching a query (from your library or search).",
                  {"type": "object", "required": ["query"], "properties": {
                      "chat_id": {"type": "integer"}, "query": {"type": "string"}}},
                  send_gif),
        make_spec("send_media",
                  "Download a direct URL and send as photo/video/file (auto-detected).",
                  {"type": "object", "required": ["url"], "properties": {
                      "chat_id": {"type": "integer"}, "url": {"type": "string"},
                      "kind": {"type": "string", "enum": ["auto", "photo", "video", "document"]}}},
                  send_media),
        make_spec("schedule_tail",
                  "Schedule a delayed follow-up message ('oh, also...') in 10..40 min by default.",
                  {"type": "object", "required": ["text"], "properties": {
                      "chat_id": {"type": "integer"}, "text": {"type": "string"},
                      "delay_min_s": {"type": "number"}, "delay_max_s": {"type": "number"}}},
                  schedule_tail),
    ]
