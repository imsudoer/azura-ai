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
        if ctx.is_duplicate(cid, msgs):
            return {"error": "duplicate", "reason": "already sent identical messages this cycle"}
        opts = {
            "reply_to": args.get("reply_to"),
            "split": bool(args.get("split", True)),
            "typing": bool(args.get("typing", True)),
        }
        res = await ctx.sender(cid, msgs, opts)
        try:
            if int((res or {}).get("sent", 0)) > 0:
                ctx.remember_sent(cid, msgs)
        except Exception:
            pass
        return res

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

    async def edit_my_message(args: dict) -> dict:
        """Edit one of your own previously sent messages (typo fix, addendum)."""
        client = ctx._tg_client
        if client is None:
            return {"error": "no telegram client"}
        cid = _coerce_target(args.get("chat_id"), default=ctx.chat_id)
        mid = args.get("message_id") or args.get("msg_id")
        new_text = str(args.get("text") or "").strip()
        if not cid or not mid or not new_text:
            return {"error": "need chat_id, message_id, text"}
        try:
            m = await client.edit_message_text(cid, int(mid), new_text)
            return {"ok": True, "id": getattr(m, "id", None)}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    async def reply_to_message(args: dict) -> dict:
        """Reply to a specific message (with the quote arrow), 1..N short messages."""
        if ctx.sender is None:
            return {"error": "sender not bound"}
        cid = _coerce_target(args.get("chat_id"), default=ctx.chat_id)
        rid = args.get("reply_to_message_id") or args.get("message_id") or args.get("reply_to")
        msgs = [str(x) for x in (args.get("messages") or []) if str(x).strip()]
        if not cid or not rid or not msgs:
            return {"error": "need chat_id, reply_to_message_id, messages"}
        if ctx.is_duplicate(cid, msgs):
            return {"error": "duplicate"}
        opts = {"reply_to": int(rid), "split": True, "typing": True}
        res = await ctx.sender(cid, msgs, opts)
        try:
            if int((res or {}).get("sent", 0)) > 0:
                ctx.remember_sent(cid, msgs)
        except Exception:
            pass
        return res

    async def react_to_message(args: dict) -> dict:
        """Put a single-emoji reaction on a message."""
        client = ctx._tg_client
        if client is None:
            return {"error": "no telegram client"}
        cid = _coerce_target(args.get("chat_id"), default=ctx.chat_id)
        mid = args.get("message_id") or args.get("msg_id")
        emoji = str(args.get("emoji") or args.get("reaction") or "")
        if not cid or not mid or not emoji:
            return {"error": "need chat_id, message_id, emoji"}
        try:
            await client.send_reaction(cid, int(mid), emoji)
            return {"ok": True}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    async def delete_my_message(args: dict) -> dict:
        """Delete one of your own messages."""
        client = ctx._tg_client
        if client is None:
            return {"error": "no telegram client"}
        cid = _coerce_target(args.get("chat_id"), default=ctx.chat_id)
        mid = args.get("message_id") or args.get("msg_id")
        if not cid or not mid:
            return {"error": "need chat_id, message_id"}
        try:
            await client.delete_messages(cid, int(mid))
            return {"ok": True}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

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
        make_spec("edit_my_message",
                  "Edit one of YOUR previously sent messages (typo fix, change wording).",
                  {"type": "object", "required": ["message_id", "text"], "properties": {
                      "chat_id": {"type": ["integer", "string"]},
                      "message_id": {"type": "integer"},
                      "text": {"type": "string"}}},
                  edit_my_message),
        make_spec("reply_to_message",
                  "Reply to a specific message (with the quote arrow). Use when answering a particular line, esp. in groups.",
                  {"type": "object", "required": ["reply_to_message_id", "messages"], "properties": {
                      "chat_id": {"type": ["integer", "string"]},
                      "reply_to_message_id": {"type": "integer"},
                      "messages": {"type": "array", "items": {"type": "string"}}}},
                  reply_to_message),
        make_spec("react_to_message",
                  "Put a single-emoji reaction on a message (❤️ / 😂 / 👀 / 🔥 etc.).",
                  {"type": "object", "required": ["message_id", "emoji"], "properties": {
                      "chat_id": {"type": ["integer", "string"]},
                      "message_id": {"type": "integer"},
                      "emoji": {"type": "string"}}},
                  react_to_message),
        make_spec("delete_my_message",
                  "Delete one of YOUR own messages.",
                  {"type": "object", "required": ["message_id"], "properties": {
                      "chat_id": {"type": ["integer", "string"]},
                      "message_id": {"type": "integer"}}},
                  delete_my_message),
    ]
