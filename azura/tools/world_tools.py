"""World-awareness tools: understand chats, users, dialogs, search archives."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec
from azura.utils.log import get_logger

log = get_logger("tools.world")


def build(ctx: ToolContext) -> list[ToolSpec]:

    async def get_chat_info(args: dict) -> dict:
        """Full info about a chat you're in."""
        client = ctx._tg_client
        if client is None:
            return {"error": "no tg client"}
        cid = int(args["chat_id"])
        out: dict = {"chat_id": cid}
        try:
            chat = await client.get_chat(cid)
            out["title"] = getattr(chat, "title", None) or getattr(chat, "first_name", None)
            out["username"] = getattr(chat, "username", None)
            out["type"] = str(getattr(getattr(chat, "type", None), "value", "unknown"))
            out["members_count"] = getattr(chat, "members_count", None)
            out["description"] = (getattr(chat, "description", None) or "")[:300]
        except Exception as e:
            out["tg_error"] = str(e)[:200]
        db_chat = await ctx.memory.repos.chats.get(cid)
        if db_chat:
            out["muted"] = db_chat.muted
            out["importance"] = db_chat.importance
            out["opinion"] = db_chat.opinion
            out["kind"] = db_chat.kind
        from azura.mind.chat_heat import chat_heat
        out["heat"] = round(await chat_heat(ctx.memory.repos, cid), 2)
        unseen = await ctx.memory.repos.messages.unseen_count(cid)
        out["unseen"] = unseen
        return out

    async def get_user_info(args: dict) -> dict:
        """What you know about a user: name, opinion, proximity, feelings, recent messages."""
        uid = int(args["user_id"])
        out: dict = {"user_id": uid}
        user_row = await ctx.memory.repos.users.get(uid)
        if user_row:
            out["username"] = user_row.username
            out["first_name"] = user_row.first_name
            out["last_name"] = user_row.last_name
            out["is_bot"] = user_row.is_bot
        op = await ctx.memory.opinions.user(uid)
        prox = await ctx.memory.opinions.proximity(uid)
        feelings = await ctx.memory.feelings.toward_user(uid)
        out["opinion"] = op
        out["proximity"] = prox.value
        out["feelings"] = {k: round(v, 2) for k, v in feelings.items()}
        last_self = await ctx.memory.repos.archive.last_self_ts(uid)
        if last_self:
            from azura.utils.timez import ts
            out["last_contact_ago_s"] = ts() - last_self
        recent = await ctx.memory.repos.archive.recent(uid, limit=8)
        out["recent_messages"] = [
            {"who": "me" if r.is_self else "them", "text": (r.text or r.caption or "")[:150]}
            for r in recent[-8:] if r.text or r.caption
        ]
        return out

    async def search_dialogs(args: dict) -> dict:
        """Search your chats by name/username substring."""
        q = str(args.get("query", "")).lower().strip()
        if not q:
            return {"error": "need query"}
        chats = await ctx.memory.repos.chats.all_active()
        hits = []
        for c in chats:
            title = (c.title or "").lower()
            uname = (c.username or "").lower()
            if q in title or q in uname or q in str(c.id):
                hits.append({
                    "chat_id": c.id, "title": c.title, "username": c.username,
                    "kind": c.kind, "muted": c.muted,
                })
            if len(hits) >= 10:
                break
        return {"results": hits, "count": len(hits)}

    async def resolve_chat(args: dict) -> dict:
        """Resolve a fuzzy chat name/nickname to a chat_id. Searches DB first, then TG."""
        q = str(args.get("query", "")).strip()
        if not q:
            return {"error": "need query"}
        ql = q.lower()
        chats = await ctx.memory.repos.chats.all_active()
        best = None
        best_score = 0
        for c in chats:
            title = (c.title or "").lower()
            uname = (c.username or "").lower()
            score = 0
            if ql == title or ql == uname:
                score = 100
            elif ql in title:
                score = 70 + (len(ql) / max(1, len(title))) * 30
            elif ql in uname:
                score = 60 + (len(ql) / max(1, len(uname))) * 30
            if score > best_score:
                best_score = score
                best = c
        if best and best_score >= 50:
            return {"chat_id": best.id, "title": best.title, "username": best.username,
                    "kind": best.kind, "score": round(best_score)}
        client = ctx._tg_client
        if client and q.startswith("@"):
            try:
                chat = await client.get_chat(q)
                return {"chat_id": chat.id, "title": getattr(chat, "title", None),
                        "username": getattr(chat, "username", None), "source": "tg_resolve"}
            except Exception:
                pass
        return {"error": f"no chat matching '{q}'", "tried": len(chats)}

    async def chat_recent_messages(args: dict) -> dict:
        """Get recent messages from a chat with author names and text."""
        cid = int(args.get("chat_id") or ctx.chat_id or 0)
        limit = min(30, int(args.get("limit", 15)))
        rows = await ctx.memory.repos.archive.recent(cid, limit=limit)
        msgs = []
        for r in rows[-limit:]:
            who = "me" if r.is_self else str(r.from_id or "?")
            if not r.is_self and r.from_id:
                u = await ctx.memory.repos.users.get(r.from_id)
                if u:
                    who = u.first_name or u.username or str(r.from_id)
            msgs.append({
                "id": r.tg_msg_id, "who": who,
                "text": (r.text or r.caption or "")[:200],
                "ts": r.ts,
            })
        return {"chat_id": cid, "messages": msgs}

    async def search_in_chat(args: dict) -> dict:
        """Full-text search in a chat's local archive (FTS5)."""
        cid = int(args.get("chat_id") or ctx.chat_id or 0)
        q = str(args.get("query", ""))
        if not q:
            return {"error": "need query"}
        rows = await ctx.memory.repos.archive.search(q, chat_id=cid, limit=int(args.get("limit", 10)))
        return {"results": [
            {"id": r.tg_msg_id, "text": (r.text or r.caption or "")[:200], "ts": r.ts,
             "is_self": r.is_self}
            for r in rows
        ]}

    async def search_global_memory(args: dict) -> dict:
        """Search your long-term memory (facts + episodes) by text."""
        q = str(args.get("query", ""))
        if not q:
            return {"error": "need query"}
        limit = int(args.get("limit", 8))
        long_hits = await ctx.memory.long.search(q, limit=limit)
        ep_hits = await ctx.memory.episodic.search(q, limit=limit)
        return {"facts": long_hits, "episodes": ep_hits}

    async def whoami(args: dict) -> dict:
        """Your own Telegram identity."""
        client = ctx._tg_client
        if client is None:
            return {"error": "no tg client"}
        me = await client.get_me()
        return {
            "id": me.id, "first_name": me.first_name, "last_name": me.last_name,
            "username": me.username, "phone": me.phone_number,
            "bio": getattr(me, "bio", None),
        }

    async def leave_chat(args: dict) -> dict:
        """Leave a group/channel. IRREVERSIBLE! Use only when you genuinely want to leave."""
        client = ctx._tg_client
        if client is None:
            return {"error": "no tg client"}
        cid = int(args["chat_id"])
        reason = args.get("reason", "")
        try:
            await client.leave_chat(cid)
            log.warning("LEFT chat {} reason={!r}", cid, reason)
            await ctx.memory.repos.journal.write(
                f"left chat {cid}: {reason}", kind="action", chat_id=cid
            )
            return {"ok": True, "left": cid}
        except Exception as e:
            return {"error": str(e)[:200]}

    async def join_chat(args: dict) -> dict:
        """Join a chat by @username or invite link."""
        client = ctx._tg_client
        if client is None:
            return {"error": "no tg client"}
        target = str(args.get("username") or args.get("link") or "")
        if not target:
            return {"error": "need username or link"}
        try:
            chat = await client.join_chat(target)
            cid = getattr(chat, "id", None)
            log.info("JOINED chat {} via {!r}", cid, target)
            return {"ok": True, "chat_id": cid, "title": getattr(chat, "title", None)}
        except Exception as e:
            return {"error": str(e)[:200]}

    async def archive_chat(args: dict) -> dict:
        """Archive a chat (move to archive folder in TG)."""
        client = ctx._tg_client
        if client is None:
            return {"error": "no tg client"}
        cid = int(args["chat_id"])
        try:
            await client.archive_chats(cid)
            return {"ok": True, "archived": cid}
        except Exception as e:
            return {"error": str(e)[:200]}

    async def pin_message(args: dict) -> dict:
        """Pin a message in a chat."""
        client = ctx._tg_client
        if client is None:
            return {"error": "no tg client"}
        cid = int(args["chat_id"])
        mid = int(args["message_id"])
        try:
            await client.pin_chat_message(cid, mid)
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)[:200]}

    async def press_inline_button(args: dict) -> dict:
        """Press an inline keyboard button on a bot message."""
        client = ctx._tg_client
        if client is None:
            return {"error": "no tg client"}
        cid = int(args["chat_id"])
        mid = int(args["message_id"])
        btn_text = args.get("button_text")
        btn_idx = args.get("button_index")
        try:
            msg = await client.get_messages(cid, mid)
            if not msg or not msg.reply_markup:
                return {"error": "no inline keyboard on that message"}
            buttons = []
            for row in msg.reply_markup.inline_keyboard:
                for btn in row:
                    buttons.append(btn)
            target = None
            if btn_text:
                for b in buttons:
                    if btn_text.lower() in (b.text or "").lower():
                        target = b
                        break
            elif btn_idx is not None:
                idx = int(btn_idx)
                if 0 <= idx < len(buttons):
                    target = buttons[idx]
            if target is None:
                return {"error": "button not found", "available": [b.text for b in buttons]}
            await msg.click(target.text)
            return {"ok": True, "clicked": target.text}
        except Exception as e:
            return {"error": str(e)[:200]}

    return [
        make_spec(
            "get_chat_info",
            "Get full info about a chat: title, type, members, description, your opinion, heat, unseen count. Use when you need context about a chat.",
            {"type": "object", "required": ["chat_id"], "properties": {
                "chat_id": {"type": "integer"}}},
            get_chat_info),
        make_spec(
            "get_user_info",
            "Everything you know about a user: name, opinion, proximity, feelings, recent messages. Call this to understand who you're talking to.",
            {"type": "object", "required": ["user_id"], "properties": {
                "user_id": {"type": "integer"}}},
            get_user_info),
        make_spec(
            "search_dialogs",
            "Search your chats by name/username substring. Returns matching chat_ids. Use to find a chat when you only know part of the name.",
            {"type": "object", "required": ["query"], "properties": {
                "query": {"type": "string"}}},
            search_dialogs),
        make_spec(
            "resolve_chat",
            "Resolve a fuzzy chat name, nickname, or @username to an exact chat_id. Use when someone says 'send it to the onlysq chat' and you need the actual ID.",
            {"type": "object", "required": ["query"], "properties": {
                "query": {"type": "string"}}},
            resolve_chat),
        make_spec(
            "chat_recent_messages",
            "Get the last N messages from a chat with author names and text. Good for catching up on what was said.",
            {"type": "object", "properties": {
                "chat_id": {"type": "integer"}, "limit": {"type": "integer"}}},
            chat_recent_messages),
        make_spec(
            "search_in_chat",
            "Full-text search in a chat's local archive. Find old messages by keywords.",
            {"type": "object", "required": ["query"], "properties": {
                "chat_id": {"type": "integer"}, "query": {"type": "string"},
                "limit": {"type": "integer"}}},
            search_in_chat),
        make_spec(
            "search_global_memory",
            "Search your own long-term memory: facts you saved, episodes you experienced. Semantic search.",
            {"type": "object", "required": ["query"], "properties": {
                "query": {"type": "string"}, "limit": {"type": "integer"}}},
            search_global_memory),
        make_spec(
            "whoami",
            "Check your own Telegram identity: name, username, bio, phone.",
            {"type": "object", "properties": {}},
            whoami),
        make_spec(
            "leave_chat",
            "PERMANENTLY leave a group or channel. This is IRREVERSIBLE. Only use if you truly want to leave — spam groups, toxic chats, or when explicitly told to.",
            {"type": "object", "required": ["chat_id"], "properties": {
                "chat_id": {"type": "integer"}, "reason": {"type": "string"}}},
            leave_chat),
        make_spec(
            "join_chat",
            "Join a chat by @username or invite link.",
            {"type": "object", "properties": {
                "username": {"type": "string"}, "link": {"type": "string"}}},
            join_chat),
        make_spec(
            "archive_chat",
            "Archive a chat (move to archive folder). Reversible.",
            {"type": "object", "required": ["chat_id"], "properties": {
                "chat_id": {"type": "integer"}}},
            archive_chat),
        make_spec(
            "pin_message",
            "Pin a message in a chat where you have permission.",
            {"type": "object", "required": ["chat_id", "message_id"], "properties": {
                "chat_id": {"type": "integer"}, "message_id": {"type": "integer"}}},
            pin_message),
        make_spec(
            "press_inline_button",
            "Press an inline keyboard button on a bot message. Specify button_text (fuzzy match) or button_index (0-based).",
            {"type": "object", "required": ["chat_id", "message_id"], "properties": {
                "chat_id": {"type": "integer"}, "message_id": {"type": "integer"},
                "button_text": {"type": "string"}, "button_index": {"type": "integer"}}},
            press_inline_button),
    ]
