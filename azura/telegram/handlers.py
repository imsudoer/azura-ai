"""Top-level message dispatcher used by run.py to register handlers."""
from __future__ import annotations

import asyncio
from typing import Any

from pyrogram import Client
from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from azura.config import Settings
from azura.constants import ChatKind
from azura.db.repo import Repos
from azura.humanize.backpressure import Backpressure
from azura.humanize.style_diversity import StyleDiversity
from azura.memory.service import MemoryService
from azura.mind.agent import Agent
from azura.mind.attention import Attention
from azura.mind.clock import snapshot
from azura.mind.conflict import ConflictEngine
from azura.mind.intent import IntentEngine
from azura.mind.mood import MoodEngine
from azura.mind.presence import PresenceEngine
from azura.mind.tails import TailQueue
from azura.mind.triggers import detect, urgency
from azura.personality.schema import Persona
from azura.telegram.media_dl import send_url
from azura.telegram.message_record import record_message
from azura.telegram.operator import handle as op_handle
from azura.telegram.reply_formatter import build_user_prompt
from azura.telegram.senders import Sender
from azura.telegram.stickers_collector import StickersCollector
from azura.tools.builder import build_registry, default_tool_subset
from azura.tools.context import ToolContext
from azura.utils.log import get_logger
from azura.utils.rng import Rng
from azura.utils.timez import ts

log = get_logger("tg.handlers")


_TG_KIND = {
    ChatType.PRIVATE: ChatKind.PRIVATE.value,
    ChatType.BOT: ChatKind.BOT.value,
    ChatType.GROUP: ChatKind.GROUP.value,
    ChatType.SUPERGROUP: ChatKind.SUPERGROUP.value,
    ChatType.CHANNEL: ChatKind.CHANNEL.value,
}


class Dispatcher:
    """Per-message handler. Opens a fresh DB session, runs the cycle, commits."""

    def __init__(
        self,
        *,
        client: Client,
        persona: Persona,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        rng: Rng,
        backpressure: Backpressure,
        style: StyleDiversity,
        mood_engine_factory,
        presence_engine_factory,
    ) -> None:
        self.client = client
        self.p = persona
        self.sm = sessionmaker
        self.s = settings
        self.rng = rng
        self.bp = backpressure
        self.style = style
        self._mood_factory = mood_engine_factory
        self._presence_factory = presence_engine_factory
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, chat_id: int) -> asyncio.Lock:
        lk = self._locks.get(chat_id)
        if lk is None:
            lk = asyncio.Lock()
            self._locks[chat_id] = lk
        return lk

    async def on_message(self, client: Client, message: Message) -> None:
        """Entry point bound to MessageHandler."""
        try:
            await self._dispatch(client, message)
        except Exception:
            log.exception("dispatch failed")

    async def on_edited(self, client: Client, message: Message) -> None:
        """Update both hot row and archive on an edit event."""
        try:
            edited_ts = int(message.edit_date.timestamp()) if message.edit_date else ts()
            new_text = message.text or message.caption
            async with self.sm() as session:
                r = Repos(session)
                await r.messages.mark_edited(message.chat.id, message.id, new_text, edited_ts)
                await r.archive.mark_edited(message.chat.id, message.id, new_text, edited_ts)
                await session.commit()
        except Exception:
            log.exception("on_edited failed")

    async def on_deleted(self, client: Client, messages: list[Message]) -> None:
        """Mark deleted_ts on every affected row."""
        now = ts()
        try:
            async with self.sm() as session:
                r = Repos(session)
                for msg in messages:
                    cid = getattr(getattr(msg, "chat", None), "id", None)
                    if cid is None:
                        continue
                    await r.messages.mark_deleted(cid, msg.id, now)
                    await r.archive.mark_deleted(cid, msg.id, now)
                await session.commit()
        except Exception:
            log.exception("on_deleted failed")

    async def on_reaction(self, client: Client, update) -> None:
        """Persist updated reactions on a message."""
        try:
            chat = getattr(update, "chat", None)
            msg_id = getattr(update, "message_id", None) or getattr(update, "msg_id", None)
            if chat is None or msg_id is None:
                return
            new = []
            for r in getattr(update, "new_reactions", None) or []:
                emoji = getattr(r, "emoji", None) or getattr(getattr(r, "reaction", None), "emoticon", None)
                if emoji:
                    new.append({"emoji": emoji})
            async with self.sm() as session:
                rr = Repos(session)
                await rr.messages.update_reactions(chat.id, msg_id, new)
                await rr.archive.update_reactions(chat.id, msg_id, new)
                await session.commit()
        except Exception:
            log.exception("on_reaction failed")

    async def _dispatch(self, client: Client, msg: Message) -> None:
        if msg.outgoing or msg.from_user is None:
            await self._persist_only(msg)
            return

        chat_kind = _TG_KIND.get(msg.chat.type, ChatKind.GROUP.value)
        if chat_kind == ChatKind.CHANNEL.value and not msg.text:
            await self._persist_only(msg)
            return

        async with self._lock(msg.chat.id):
            async with self.sm() as session:
                await self._run_cycle(client, msg, session, chat_kind)

    async def _persist_only(self, msg: Message) -> None:
        async with self.sm() as session:
            r = Repos(session)
            chat_kind = _TG_KIND.get(msg.chat.type, ChatKind.GROUP.value)
            await record_message(self.client, r, msg, chat_kind=chat_kind, is_self=bool(msg.outgoing))
            await session.commit()

    async def _run_cycle(self, client: Client, msg: Message, session: AsyncSession, chat_kind: str) -> None:
        r = Repos(session)
        m = MemoryService(r)
        await record_message(client, r, msg, chat_kind=chat_kind, is_self=bool(msg.outgoing))

        if await op_handle(client, msg, ctx=self._make_ctx(client, m, r, msg, partial=True), settings=self.s):
            await session.commit()
            return

        mood_eng = self._mood_factory(self.p, m, rng=self.rng)
        presence_eng = self._presence_factory(self.p, m, rng=self.rng)
        intent_eng = IntentEngine(self.p, m, rng=self.rng)
        att = Attention(self.p, r, m)
        conflict = ConflictEngine(self.p, m)
        tails = TailQueue(self.p, m, rng=self.rng)
        collector = StickersCollector(self.p, m)
        if msg.sticker:
            await collector.on_sticker(msg)
        if msg.animation:
            await collector.on_animation(msg)

        clk = snapshot(self.p)
        mood = await mood_eng.now()
        presence = await presence_eng.current()
        if presence.state.value in ("asleep", "offline"):
            await session.commit()
            return

        me = await client.get_me()
        own_username = me.username
        text = (msg.text or msg.caption or "").strip()
        reply_to_self = bool(msg.reply_to_message and msg.reply_to_message.from_user
                             and msg.reply_to_message.from_user.id == me.id)
        trig = detect(persona=self.p, text=text, own_username=own_username, reply_to_self=reply_to_self)

        in_private = chat_kind in (ChatKind.PRIVATE.value, ChatKind.BOT.value)
        decision = await intent_eng.decide_reply(
            chat_id=msg.chat.id,
            from_user_id=(msg.from_user.id if msg.from_user else None),
            text=text, trigger=trig, mood=mood, in_private=in_private,
        )
        log.info("intent chat={} decision={} score={:.2f} reason='{}'",
                 msg.chat.id, decision.decision, decision.score, decision.reason)

        if decision.decision in ("ignore", "later"):
            await session.commit()
            return
        if decision.decision == "read_only":
            await client.read_chat_history(msg.chat.id)
            await session.commit()
            return
        if decision.decision == "react":
            try:
                await client.send_reaction(msg.chat.id, msg.id, "👀")
            except Exception:
                pass
            await session.commit()
            return

        sender = Sender(
            client, persona=self.p, memory=m, rng=self.rng,
            backpressure=self.bp, style=self.style,
        )
        ctx = self._make_ctx(client, m, r, msg, sender=sender)
        registry = build_registry(ctx)
        tools = default_tool_subset(registry)
        agent = Agent(self.p, m)

        user_prompt = await build_user_prompt(
            memory=m,
            chat_id=msg.chat.id,
            from_user_id=(msg.from_user.id if msg.from_user else None),
            text=text, trigger=trig, in_private=in_private,
            incoming_tg_msg_id=msg.id,
            reply_to_text=(msg.reply_to_message.text if msg.reply_to_message else None),
        )
        situation = {
            "chat_id": msg.chat.id,
            "chat_kind": chat_kind,
            "in_private": in_private,
            "from_user_id": (msg.from_user.id if msg.from_user else None),
            "urgency": round(urgency(trig), 2),
            "presence": presence.state.value,
            "clock_phase": clk.phase,
        }
        result = await agent.run(
            mood=mood, situation=situation, user_prompt=user_prompt,
            tools=tools, max_steps=4,
        )
        if result.messages:
            await sender.send(
                msg.chat.id, result.messages,
                mood=mood, clock=clk,
                in_private=in_private, urgency=urgency(trig),
                reply_to=msg.id if not in_private else None,
            )
        await session.commit()

    def _make_ctx(
        self,
        client: Client,
        memory: MemoryService,
        repos: Repos,
        msg: Message,
        *,
        sender: Sender | None = None,
        partial: bool = False,
    ) -> ToolContext:
        from azura.mind.mood import MoodEngine
        from azura.mind.presence import PresenceEngine
        from azura.mind.conflict import ConflictEngine
        from azura.mind.tails import TailQueue
        mood = MoodEngine(self.p, memory, rng=self.rng)
        presence = PresenceEngine(self.p, memory, rng=self.rng)
        conflict = ConflictEngine(self.p, memory)
        tails = TailQueue(self.p, memory, rng=self.rng)
        ctx = ToolContext(
            persona=self.p, memory=memory, mood=mood, presence=presence,
            conflict=conflict, tails=tails,
            chat_id=msg.chat.id if msg and msg.chat else None,
            user_id=msg.from_user.id if msg and msg.from_user else None,
            _tg_client=client,
        )
        if partial:
            return ctx
        if sender is not None:
            async def _sender(chat_id: int, messages: list[str], opts: dict) -> dict:
                clk = snapshot(self.p)
                mood_view = await mood.now()
                res = await sender.send(
                    chat_id, messages, mood=mood_view, clock=clk,
                    in_private=(opts.get("in_private", True)),
                    urgency=float(opts.get("urgency", 0.2)),
                    reply_to=opts.get("reply_to"),
                    do_split=bool(opts.get("split", True)),
                )
                return {"sent": res.sent, "skipped": res.skipped}
            ctx.sender = _sender

            async def _sticker_sender(chat_id: int, query: str) -> dict:
                mv = await mood.now()
                items = await memory.repos.stickers.pick_by_mood(
                    valence=mv.valence, arousal=mv.arousal, limit=3,
                )
                if not items:
                    return {"ok": False, "reason": "no stickers"}
                pick = items[0]
                m = await client.send_sticker(chat_id, pick.file_id)
                await memory.repos.stickers.mark_used(pick.id)
                return {"ok": True, "msg_id": m.id, "file_id": pick.file_id}
            ctx.sticker_sender = _sticker_sender

            async def _gif_sender(chat_id: int, query: str) -> dict:
                items = await memory.repos.gifs.pick_by_tags(
                    [t.strip() for t in query.split(",") if t.strip()], limit=3,
                )
                if not items:
                    return {"ok": False, "reason": "no gifs"}
                pick = items[0]
                msg = await client.send_animation(chat_id, pick.file_id)
                await memory.repos.gifs.mark_used(pick.id)
                return {"ok": True, "msg_id": msg.id, "file_id": pick.file_id}
            ctx.gif_sender = _gif_sender

            async def _media_sender(chat_id: int, url: str, kind: str) -> dict:
                return await send_url(client, chat_id, url, kind=kind)
            ctx.media_sender = _media_sender

            async def _web_search(query: str) -> list[dict]:
                from azura.tools.web_impl import ddg_search
                return await ddg_search(query)
            ctx.web_searcher = _web_search

            async def _web_fetch(url: str) -> str:
                from azura.tools.web_impl import fetch_text
                return await fetch_text(url)
            ctx.web_fetcher = _web_fetch
        return ctx


def register(dispatcher: Dispatcher, client: Client) -> None:
    """Attach the dispatcher to the kurigram client (message + edited + deleted + reaction)."""
    from pyrogram.handlers import (
        DeletedMessagesHandler,
        EditedMessageHandler,
        MessageReactionHandler,
    )
    client.add_handler(MessageHandler(dispatcher.on_message, filters.all))
    client.add_handler(EditedMessageHandler(dispatcher.on_edited, filters.all))
    client.add_handler(DeletedMessagesHandler(dispatcher.on_deleted))
    try:
        client.add_handler(MessageReactionHandler(dispatcher.on_reaction))
    except Exception:
        pass
