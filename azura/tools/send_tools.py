"""Send-content tools: text bursts, stickers, gifs, photos by URL, tails."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def _coerce_target(value, *, default=None):
    """Accept int, numeric-string, or @username/title-string; return as int or stripped str.

    Telegram client methods accept both numeric ids and @usernames, so we pass
    strings through unchanged (minus the leading @). Empty / None / 0 falls back
    to `default`.
    """
    if value is None or value == "":
        return default
    if isinstance(value, int):
        return value if value != 0 else default
    s = str(value).strip()
    if not s:
        return default
    if s.lstrip("-").isdigit():
        try:
            n = int(s)
            return n if n != 0 else default
        except ValueError:
            return default
    return s.lstrip("@")


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Outbound message tools."""

    async def send_messages(args: dict) -> dict:
        if ctx.sender is None:
            return {"error": "sender not bound"}
        cid = _coerce_target(args.get("chat_id"), default=ctx.chat_id)
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
        cid = _coerce_target(args.get("chat_id"), default=ctx.chat_id)
        if not cid:
            return {"error": "no chat target"}
        return await ctx.sticker_sender(cid, str(args.get("query") or args.get("mood", "")))

    async def send_gif(args: dict) -> dict:
        if ctx.gif_sender is None:
            return {"error": "gif sender not bound"}
        cid = _coerce_target(args.get("chat_id"), default=ctx.chat_id)
        if not cid:
            return {"error": "no chat target"}
        return await ctx.gif_sender(cid, str(args["query"]))

    async def send_media(args: dict) -> dict:
        if ctx.media_sender is None:
            return {"error": "media sender not bound"}
        cid = _coerce_target(args.get("chat_id"), default=ctx.chat_id)
        if not cid:
            return {"error": "no chat target"}
        return await ctx.media_sender(cid, str(args["url"]), str(args.get("kind", "auto")))

    async def schedule_tail(args: dict) -> dict:
        raw = args.get("chat_id") or ctx.chat_id
        try:
            cid = int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            return {"error": "schedule_tail needs numeric chat_id"}
        if not cid:
            return {"error": "no chat target"}
        delay_min = float(args.get("delay_min_s", 10 * 60))
        delay_max = float(args.get("delay_max_s", 40 * 60))
        item = ctx.tails.schedule(cid, str(args["text"]), delay_min, delay_max)
        return {"due_ts": item.due_ts}

    return [
        make_spec("send_messages",
                  "Send 1..N short messages to a chat. `chat_id` may be a numeric Telegram id OR a username string like 'rriinnaass' (without '@'). To reply in the SAME chat you're currently reading, omit chat_id entirely. NEVER use placeholder strings like 'operator' or 'user' — those are not chat ids.",
                  {"type": "object", "required": ["messages"], "properties": {
                      "chat_id": {"type": ["integer", "string"]},
                      "messages": {"type": "array", "items": {"type": "string"}},
                      "reply_to": {"type": "integer"},
                      "split": {"type": "boolean"},
                      "typing": {"type": "boolean"}}},
                  send_messages),
        make_spec("send_sticker",
                  "Send a sticker matching a free-form mood/topic query. chat_id may be int id or @username string.",
                  {"type": "object", "properties": {
                      "chat_id": {"type": ["integer", "string"]},
                      "query": {"type": "string"},
                      "mood": {"type": "string"}}},
                  send_sticker),
        make_spec("send_gif",
                  "Send a GIF matching a query. chat_id may be int id or username string.",
                  {"type": "object", "required": ["query"], "properties": {
                      "chat_id": {"type": ["integer", "string"]}, "query": {"type": "string"}}},
                  send_gif),
        make_spec("send_media",
                  "Download a direct URL and send as photo/video/file. chat_id may be int id or username string.",
                  {"type": "object", "required": ["url"], "properties": {
                      "chat_id": {"type": ["integer", "string"]}, "url": {"type": "string"},
                      "kind": {"type": "string", "enum": ["auto", "photo", "video", "document"]}}},
                  send_media),
        make_spec("schedule_tail",
                  "Schedule a delayed follow-up message ('oh, also...') in 10..40 min by default.",
                  {"type": "object", "required": ["text"], "properties": {
                      "chat_id": {"type": "integer"}, "text": {"type": "string"},
                      "delay_min_s": {"type": "number"}, "delay_max_s": {"type": "number"}}},
                  schedule_tail),
    ]
