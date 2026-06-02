"""Self-control tools: presence, mood, journal, reactions, saved-messages, self-introspection."""
from __future__ import annotations

from azura.constants import Presence
from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Build self-control tool specs bound to ctx."""

    async def go_afk(args: dict) -> dict:
        minutes = int(args.get("minutes", 10))
        reason = str(args.get("reason", "stepping away"))
        v = await ctx.presence.go_afk(minutes, reason)
        return {"state": v.state.value, "until_ts": v.until_ts}

    async def come_back(_: dict) -> dict:
        v = await ctx.presence.come_back()
        return {"state": v.state.value}

    async def set_presence(args: dict) -> dict:
        s = Presence(args["state"])
        v = await ctx.presence.set(s, reason=args.get("reason"), until_ts=args.get("until_ts"))
        return {"state": v.state.value}

    async def nudge_mood(args: dict) -> dict:
        v = await ctx.mood.nudge(
            valence=float(args.get("valence", 0.0)),
            arousal=float(args.get("arousal", 0.0)),
            stress=float(args.get("stress", 0.0)),
            note=args.get("note"),
        )
        return v.__dict__

    async def journal(args: dict) -> dict:
        text = str(args.get("text") or args.get("content") or "").strip()
        if not text:
            return {"error": "empty text"}
        await ctx.memory.repos.journal.write(
            text,
            kind=str(args.get("kind", "thought")),
            chat_id=args.get("chat_id") or ctx.chat_id,
            user_id=args.get("user_id"),
        )
        return {"ok": True}

    async def set_reaction(args: dict) -> dict:
        """Put an emoji reaction on a specific message."""
        if ctx._tg_client is None:
            return {"error": "no telegram client"}
        cid = args.get("chat_id") or ctx.chat_id
        mid = args.get("message_id") or args.get("msg_id")
        emoji = str(args.get("emoji") or args.get("reaction") or "")
        if not cid or not mid or not emoji:
            return {"error": "need chat_id, message_id, emoji"}
        try:
            await ctx._tg_client.send_reaction(cid, mid, emoji)
            return {"ok": True}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    async def save_to_favorites(args: dict) -> dict:
        """Forward something into Saved Messages, or post a free-text note there."""
        if ctx._tg_client is None:
            return {"error": "no telegram client"}
        text = args.get("text")
        from_chat = args.get("from_chat_id") or args.get("chat_id")
        message_id = args.get("message_id") or args.get("msg_id")
        try:
            if from_chat and message_id:
                m = await ctx._tg_client.forward_messages("me", from_chat, message_id)
                return {"ok": True, "kind": "forwarded", "id": getattr(m, "id", None)}
            if text:
                m = await ctx._tg_client.send_message("me", str(text))
                return {"ok": True, "kind": "text", "id": getattr(m, "id", None)}
            return {"error": "need text or (from_chat_id+message_id)"}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    async def read_chat(args: dict) -> dict:
        """Mark a chat as read."""
        if ctx._tg_client is None:
            return {"error": "no telegram client"}
        cid = args.get("chat_id") or ctx.chat_id
        if not cid:
            return {"error": "no chat_id"}
        try:
            await ctx._tg_client.read_chat_history(cid)
            return {"ok": True}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    async def unread_dialogs(args: dict) -> dict:
        """List dialogs with unread messages so she can decide whom to answer first."""
        if ctx._tg_client is None:
            return {"error": "no telegram client"}
        limit = int(args.get("limit", 15))
        out: list[dict] = []
        try:
            async for d in ctx._tg_client.get_dialogs(limit=limit * 3):
                if not getattr(d, "unread_messages_count", 0):
                    continue
                chat = d.chat
                out.append({
                    "chat_id": chat.id,
                    "title": getattr(chat, "title", None) or getattr(chat, "first_name", None) or "",
                    "username": getattr(chat, "username", None),
                    "unread": d.unread_messages_count,
                    "kind": getattr(chat.type, "value", "unknown") if hasattr(chat, "type") else "unknown",
                })
                if len(out) >= limit:
                    break
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
        return {"items": out}

    async def view_my_profile(_: dict) -> dict:
        """Look at current first_name/last_name/bio/username/has_photo."""
        if ctx._tg_client is None:
            return {"error": "no telegram client"}
        try:
            me = await ctx._tg_client.get_me()
            has_photo = False
            try:
                async for _p in ctx._tg_client.get_chat_photos("me", limit=1):
                    has_photo = True
                    break
            except Exception:
                pass
            return {
                "id": me.id, "first_name": me.first_name, "last_name": me.last_name,
                "username": me.username, "phone_number": me.phone_number,
                "bio": getattr(me, "bio", None), "has_photo": has_photo,
            }
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    async def note_about_person(args: dict) -> dict:
        """Quick remember a fact about a user: shorthand for memory.long.add_fact."""
        text = str(args.get("text") or args.get("note") or "").strip()
        if not text:
            return {"error": "empty note"}
        uid = args.get("user_id")
        try:
            uid_int = int(uid) if uid is not None else None
        except (TypeError, ValueError):
            uid_int = None
        emb = None
        try:
            emb = await ctx.memory.embeds.get(text)
        except Exception:
            pass
        mid = await ctx.memory.long.add_fact(
            text, user_id=uid_int, topic=str(args.get("topic", "person")),
            importance=float(args.get("importance", 0.5)),
            confidence=float(args.get("confidence", 0.7)),
            embedding=emb,
        )
        return {"id": mid}

    return [
        make_spec("go_afk",
                  "Step away with an in-character reason (e.g. 'making coffee', 'tiktok rabbit hole'). Sets AFK.",
                  {"type": "object", "required": ["minutes", "reason"], "properties": {
                      "minutes": {"type": "integer"}, "reason": {"type": "string"}}},
                  go_afk),
        make_spec("come_back", "Return from AFK to ONLINE.",
                  {"type": "object", "properties": {}}, come_back),
        make_spec("set_presence",
                  "Force a presence state. Avoid 'asleep' during work hours.",
                  {"type": "object", "required": ["state"], "properties": {
                      "state": {"type": "string", "enum": ["online", "offline", "afk", "busy", "asleep"]},
                      "reason": {"type": "string"}, "until_ts": {"type": "integer"}}},
                  set_presence),
        make_spec("nudge_mood",
                  "Apply a small mood delta (valence -1..1, arousal/stress 0..1). Use after impactful moments.",
                  {"type": "object", "properties": {
                      "valence": {"type": "number"}, "arousal": {"type": "number"},
                      "stress": {"type": "number"}, "note": {"type": "string"}}},
                  nudge_mood),
        make_spec("journal",
                  "Write a private inner journal line in first person (no one sees this in chat).",
                  {"type": "object", "required": ["text"], "properties": {
                      "text": {"type": "string"}, "kind": {"type": "string"},
                      "chat_id": {"type": "integer"}, "user_id": {"type": "integer"}}},
                  journal),
        make_spec("set_reaction",
                  "Put a single-emoji reaction on a message in any chat.",
                  {"type": "object", "required": ["emoji"], "properties": {
                      "chat_id": {"type": ["integer", "string"]},
                      "message_id": {"type": "integer"},
                      "emoji": {"type": "string"}}},
                  set_reaction),
        make_spec("save_to_favorites",
                  "Forward a message into Saved Messages, OR post a free-form text note there. Use this as a personal scratchpad / aesthetic feed.",
                  {"type": "object", "properties": {
                      "text": {"type": "string"},
                      "from_chat_id": {"type": ["integer", "string"]},
                      "message_id": {"type": "integer"}}},
                  save_to_favorites),
        make_spec("read_chat", "Mark a chat as read without replying.",
                  {"type": "object", "properties": {"chat_id": {"type": ["integer", "string"]}}},
                  read_chat),
        make_spec("unread_dialogs",
                  "See which dialogs have unread messages so you can decide whom to reply to first.",
                  {"type": "object", "properties": {"limit": {"type": "integer"}}},
                  unread_dialogs),
        make_spec("view_my_profile",
                  "Look at your current Telegram profile (first/last/username/bio/has_photo).",
                  {"type": "object", "properties": {}}, view_my_profile),
        make_spec("note_about_person",
                  "Quickly remember a fact/observation about someone in your long-term memory.",
                  {"type": "object", "required": ["text"], "properties": {
                      "text": {"type": "string"}, "user_id": {"type": "integer"},
                      "topic": {"type": "string"},
                      "importance": {"type": "number"}, "confidence": {"type": "number"}}},
                  note_about_person),
    ]
