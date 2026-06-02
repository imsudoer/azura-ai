"""Operator tools exposed only via the operator channel."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec
from azura.utils.timez import ts


def _norm_username(s: str) -> str:
    return str(s or "").lstrip("@").strip().lower()


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Operator-only utilities (status, force sleep/wake, recall, help)."""

    async def status(_: dict) -> dict:
        mood = await ctx.mood.now()
        pres = await ctx.presence.current()
        return {
            "mood": mood.__dict__,
            "presence": {"state": pres.state.value, "reason": pres.reason, "until_ts": pres.until_ts},
        }

    async def force_sleep(_: dict) -> dict:
        from azura.constants import Presence
        v = await ctx.presence.set(Presence.ASLEEP, reason="forced by operator")
        return {"state": v.state.value}

    async def force_wake(_: dict) -> dict:
        from azura.constants import Presence
        v = await ctx.presence.set(Presence.ONLINE, reason="forced wake")
        return {"state": v.state.value}

    async def journal_tail(args: dict) -> dict:
        items = await ctx.memory.repos.journal.recent(limit=int(args.get("limit", 30)))
        return {"items": [{"ts": it.ts, "kind": it.kind, "text": it.text} for it in items]}

    async def help_(_: dict) -> dict:
        """Return a human-readable cheatsheet of operator capabilities."""
        return {
            "slash_commands": {
                "<SECRET> status": "current mood + presence",
                "<SECRET> sleep": "force sleep",
                "<SECRET> wake": "force wake",
                "<SECRET> journal [N]": "last N journal entries (default 10)",
                "<SECRET> pause / resume": "set presence offline / online",
                "<SECRET> rebootstrap": "regenerate name + bio + username + avatar",
                "<SECRET> regen_portrait": "regenerate only the avatar",
                "<SECRET> set_name X / set_username X": "direct profile edits",
                "<SECRET> ban N / unban N": "block / unblock a user id or @username",
            },
            "natural_language_examples": [
                "напиши @username привет",
                "напиши @username, познакомься (она выдумает причину)",
                "напиши @username, скажи что от меня",
                "что ты написала Карине? / о чём вы говорили с @user?",
                "покажи последние твои сообщения",
                "поменяй мне имя на X / фамилию Y / био Z",
                "забань @username / разбань 12345",
                "скрой last seen от @username",
                "присылай мне отчёты по @user (запоминается как директива)",
                "перегенерируй аватарку",
                "как у тебя настроение? / как день прошёл?",
            ],
            "introspection_tools": [
                "op_recent_outgoing — что ты сама недавно писала",
                "op_recent_conversation_with — переписка с конкретным человеком",
                "op_chat_summary — краткий пересказ диалога",
                "op_status / op_journal — настроение/дневник",
            ],
        }

    async def recent_outgoing(args: dict) -> dict:
        """Return persona's own recent outgoing messages, optionally scoped to a chat."""
        limit = int(args.get("limit", 20))
        target_chat = args.get("chat_id") or args.get("with") or args.get("username")
        repo = ctx.memory.repos.archive
        rows = []
        if target_chat is not None:
            cid = await _resolve_chat_id(ctx, target_chat)
            if cid is None:
                return {"error": f"cannot resolve chat {target_chat!r}"}
            recent = await repo.recent(cid, limit=200)
            rows = [a for a in recent if a.is_self][-limit:]
        else:
            from sqlalchemy import select
            from azura.db.models import ChatArchive
            r = await ctx.memory.repos.s.execute(
                select(ChatArchive)
                .where(ChatArchive.is_self.is_(True))
                .order_by(ChatArchive.ts.desc())
                .limit(limit)
            )
            rows = list(reversed(r.scalars().all()))
        return {
            "items": [
                {"chat_id": a.chat_id, "ts": a.ts, "text": (a.text or a.caption or ""),
                 "kind": a.kind}
                for a in rows
            ]
        }

    async def recent_conversation_with(args: dict) -> dict:
        """Last N messages in the chat with a user identified by id, @username, or name."""
        who = args.get("user") or args.get("username") or args.get("chat_id") or args.get("with")
        if who is None:
            return {"error": "specify user / username / chat_id"}
        limit = int(args.get("limit", 30))
        cid = await _resolve_chat_id(ctx, who)
        if cid is None:
            return {"error": f"cannot resolve {who!r}"}
        recent = await ctx.memory.repos.archive.recent(cid, limit=limit)
        return {
            "chat_id": cid,
            "items": [
                {"ts": a.ts, "from": ("me" if a.is_self else a.from_id),
                 "text": (a.text or a.caption or ""), "kind": a.kind,
                 "edited": bool(a.edited_ts), "deleted": bool(a.deleted_ts)}
                for a in recent
            ],
        }

    async def chat_summary(args: dict) -> dict:
        """Quick stats + first/last messages of a chat (no LLM call, just facts)."""
        who = args.get("user") or args.get("username") or args.get("chat_id") or args.get("with")
        if who is None:
            return {"error": "specify chat_id / user / username"}
        cid = await _resolve_chat_id(ctx, who)
        if cid is None:
            return {"error": f"cannot resolve {who!r}"}
        recent = await ctx.memory.repos.archive.recent(cid, limit=200)
        if not recent:
            return {"chat_id": cid, "empty": True}
        first = recent[0]
        last = recent[-1]
        msg_count = len(recent)
        self_count = sum(1 for a in recent if a.is_self)
        their_count = msg_count - self_count
        return {
            "chat_id": cid,
            "messages_total_window": msg_count,
            "her_messages": self_count,
            "their_messages": their_count,
            "first_in_window": {"ts": first.ts, "text": (first.text or first.caption or "")[:200],
                                "from": "me" if first.is_self else first.from_id},
            "last_in_window": {"ts": last.ts, "text": (last.text or last.caption or "")[:200],
                               "from": "me" if last.is_self else last.from_id},
        }

    return [
        make_spec("op_status", "Mood + presence snapshot.",
                  {"type": "object", "properties": {}}, status),
        make_spec("op_force_sleep", "Force persona to sleep.",
                  {"type": "object", "properties": {}}, force_sleep),
        make_spec("op_force_wake", "Force persona to wake up.",
                  {"type": "object", "properties": {}}, force_wake),
        make_spec("op_journal", "Recent journal entries.",
                  {"type": "object", "properties": {"limit": {"type": "integer"}}}, journal_tail),
        make_spec("op_help", "Cheatsheet of all operator commands + NL examples.",
                  {"type": "object", "properties": {}}, help_),
        make_spec(
            "op_recent_outgoing",
            "What did the persona herself recently write (optionally scoped to one chat/user).",
            {"type": "object", "properties": {
                "limit": {"type": "integer"},
                "chat_id": {"type": ["integer", "string"]},
                "with": {"type": ["integer", "string"]},
                "username": {"type": "string"}}},
            recent_outgoing,
        ),
        make_spec(
            "op_recent_conversation_with",
            "Last N messages of the conversation with a given user (id, @username, or first name).",
            {"type": "object", "required": [], "properties": {
                "user": {"type": ["integer", "string"]},
                "username": {"type": "string"},
                "chat_id": {"type": ["integer", "string"]},
                "with": {"type": ["integer", "string"]},
                "limit": {"type": "integer"}}},
            recent_conversation_with,
        ),
        make_spec(
            "op_chat_summary",
            "Quick chat stats + first/last messages with a user (no LLM, just facts).",
            {"type": "object", "properties": {
                "user": {"type": ["integer", "string"]},
                "username": {"type": "string"},
                "chat_id": {"type": ["integer", "string"]},
                "with": {"type": ["integer", "string"]}}},
            chat_summary,
        ),
    ]


async def _resolve_chat_id(ctx: ToolContext, raw) -> int | None:
    """Resolve a chat_id from int/numeric-string/@username/first-name."""
    if isinstance(raw, int):
        return raw
    s = str(raw or "").strip()
    if not s:
        return None
    if s.lstrip("-").isdigit():
        try:
            return int(s)
        except ValueError:
            return None
    s = s.lstrip("@")
    repo_users = ctx.memory.repos.users
    user = await repo_users.find_by_username(s) if hasattr(repo_users, "find_by_username") else None
    if user is None and ctx._tg_client is not None:
        try:
            u = await ctx._tg_client.get_users(s)
            if u and getattr(u, "id", None):
                return int(u.id)
        except Exception:
            return None
    if user is not None:
        return int(user.id)
    return None
