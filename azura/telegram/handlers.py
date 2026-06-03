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
        self._cooldown: dict[int, int] = {}
        self.typing_watcher = None
        from azura.telegram.coalescer import Coalescer
        from azura.config import get_settings as _gs
        try:
            _cfg = _gs()
            _wait = float(getattr(_cfg, "coalesce_wait_s", 4.5))
            _max = float(getattr(_cfg, "coalesce_max_wait_s", 9.0))
        except Exception:
            _wait, _max = 4.5, 9.0
        self._coalescer = Coalescer(self._coalesced_cycle, wait_s=_wait, max_wait_s=_max)

    def _lock(self, chat_id: int) -> asyncio.Lock:
        lk = self._locks.get(chat_id)
        if lk is None:
            lk = asyncio.Lock()
            self._locks[chat_id] = lk
        return lk

    async def on_message(self, client: Client, message: Message) -> None:
        """Entry point bound to MessageHandler."""
        try:
            cid = getattr(getattr(message, "chat", None), "id", None)
            uid = getattr(getattr(message, "from_user", None), "id", None)
            if self.typing_watcher is not None and cid is not None and uid is not None:
                self.typing_watcher.clear(cid, uid)
        except Exception:
            pass
        try:
            await self._dispatch(client, message)
        except Exception:
            log.exception("dispatch failed")

    async def on_raw_update(self, client: Client, update, users, chats) -> None:
        """Catch UpdateUserTyping / UpdateChatUserTyping to feed the typing watcher."""
        cls_name = update.__class__.__name__
        log.trace("raw update: {}", cls_name) if hasattr(log, "trace") else log.debug("raw update: {}", cls_name)
        if self.typing_watcher is None:
            return
        if cls_name not in ("UpdateUserTyping", "UpdateChatUserTyping", "UpdateChannelUserTyping"):
            return
        try:
            chat_id = (
                getattr(update, "user_id", None)
                if cls_name == "UpdateUserTyping"
                else getattr(update, "chat_id", None) or getattr(update, "channel_id", None)
            )
            from_peer = getattr(update, "from_id", None)
            user_id = None
            if from_peer is not None:
                user_id = (
                    getattr(from_peer, "user_id", None)
                    or getattr(from_peer, "channel_id", None)
                    or getattr(from_peer, "chat_id", None)
                )
            if user_id is None and cls_name == "UpdateUserTyping":
                user_id = getattr(update, "user_id", None)
            action = update.__class__.__name__ if not hasattr(update, "action") else update.action.__class__.__name__
            if "Typing" not in action and "SendMessage" not in action and "Upload" not in action:
                return
            if cls_name == "UpdateChannelUserTyping":
                chat_id = -1000000000000 - int(getattr(update, "channel_id", 0))
            if chat_id is None or user_id is None:
                return
            self.typing_watcher.note_typing(int(chat_id), int(user_id))
        except Exception:
            log.debug("on_raw_update typing parse failed", exc_info=True)

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

        await self._persist_only(msg)

        try:
            await self._maybe_read_if_awaiting(msg)
        except Exception:
            log.debug("awaiting-read check failed", exc_info=True)

        await self._coalescer.submit(msg.chat.id, msg)

    async def _coalesced_cycle(self, msg: Message) -> None:
        chat_kind = _TG_KIND.get(msg.chat.type, ChatKind.GROUP.value)
        async with self._lock(msg.chat.id):
            async with self.sm() as session:
                await self._run_cycle(self.client, msg, session, chat_kind)

    async def drain(self) -> None:
        """Test helper: synchronously run any pending coalesced cycle right now.

        Avoids the debounce sleep so tests don't need real-time waits.
        """
        for chat_id, slot in list(self._coalescer._slots.items()):
            if slot.timer is not None and not slot.timer.done():
                slot.timer.cancel()
                slot.timer = None
            if slot.last_msg is not None:
                msg = slot.last_msg
                slot.last_msg = None
                slot.pending_ids = []
                slot.first_ts = 0.0
                slot.runner_cancellable = True
                await self._coalesced_cycle(msg)

    async def wait_idle(self, timeout: float = 30.0) -> None:
        """Test helper: block until coalescer has no pending timers/runners."""
        import time as _t
        end = _t.monotonic() + timeout
        while _t.monotonic() < end:
            await asyncio.sleep(0.05)
            busy = False
            for slot in list(self._coalescer._slots.values()):
                if slot.timer is not None and not slot.timer.done():
                    busy = True
                    break
                if slot.runner is not None and not slot.runner.done():
                    busy = True
                    break
            if not busy:
                return

    async def _persist_only(self, msg: Message) -> None:
        async with self.sm() as session:
            r = Repos(session)
            chat_kind = _TG_KIND.get(msg.chat.type, ChatKind.GROUP.value)
            await record_message(self.client, r, msg, chat_kind=chat_kind, is_self=bool(msg.outgoing))
            await session.commit()

    async def _fetch_my_chat_role(self, client, chat_id: int, chat_kind: str, my_id: int) -> dict:
        """Return {status, can_send_text, can_send_media, can_send_polls, can_invite, is_muted}.

        Caches per chat for 5 minutes.
        """
        from azura.utils.timez import ts as _ts
        if not hasattr(self, "_role_cache"):
            self._role_cache: dict[int, tuple[int, dict]] = {}
        now = _ts()
        cached = self._role_cache.get(chat_id)
        if cached and now - cached[0] < 300:
            return cached[1]
        out: dict = {"status": "member"}
        if chat_kind in ("private", "bot"):
            out = {"status": "self"}
            self._role_cache[chat_id] = (now, out)
            return out
        try:
            cm = await client.get_chat_member(chat_id, my_id)
            status = getattr(getattr(cm, "status", None), "value", None) or str(getattr(cm, "status", "member"))
            perms = getattr(cm, "permissions", None) or getattr(cm, "privileges", None)
            def _p(attr):
                return bool(getattr(perms, attr, True)) if perms is not None else True
            out = {
                "status": status,
                "can_send_text": _p("can_send_messages"),
                "can_send_media": _p("can_send_media_messages") and _p("can_send_photos"),
                "can_send_polls": _p("can_send_polls"),
                "can_invite": _p("can_invite_users"),
                "is_admin": status in ("administrator", "creator"),
            }
        except Exception as e:
            log.debug("get_chat_member failed chat={} err={}", chat_id, e)
        self._role_cache[chat_id] = (now, out)
        return out

    async def _maybe_read_if_awaiting(self, msg: Message) -> None:
        """If she sent a message in this chat within the last AWAITING_S seconds,
        treat this incoming as a follow-up and mark read immediately. Rate-limited
        to at most once per chat per 30 seconds to avoid pinging activity to TG.
        """
        AWAITING_S = 180
        RATE_LIMIT_S = 30
        from azura.utils.timez import ts as _ts
        from sqlalchemy import select, func
        from azura.db.models import ChatArchive
        if not hasattr(self, "_awaiting_read_last"):
            self._awaiting_read_last = {}
        now = _ts()
        last = self._awaiting_read_last.get(msg.chat.id, 0)
        if now - last < RATE_LIMIT_S:
            return
        async with self.sm() as session:
            q = (
                select(func.max(ChatArchive.ts))
                .where(ChatArchive.chat_id == msg.chat.id)
                .where(ChatArchive.is_self.is_(True))
            )
            r = await session.execute(q)
            last_self = r.scalar()
        if not last_self:
            return
        if now - int(last_self) > AWAITING_S:
            return
        try:
            await self.client.read_chat_history(msg.chat.id)
            self._awaiting_read_last[msg.chat.id] = now
            log.info(
                "awaiting-read chat={} (last_self {}s ago)",
                msg.chat.id, now - int(last_self),
            )
        except Exception as e:
            log.debug("awaiting read_chat_history failed: {}", e)

    async def _run_cycle(self, client: Client, msg: Message, session: AsyncSession, chat_kind: str) -> None:
        r = Repos(session)
        m = MemoryService(r)
        await record_message(client, r, msg, chat_kind=chat_kind, is_self=bool(msg.outgoing))
        await session.commit()

        is_operator = bool(msg.from_user and msg.from_user.id == self.s.operator_id)

        if not is_operator:
            from azura.utils.timez import ts as _ts
            now = _ts()
            exp = self._cooldown.get(msg.chat.id)
            if exp is not None and exp > now:
                log.info("chat {} in cooldown ({}s left), skip LLM",
                         msg.chat.id, exp - now)
                return
            if exp is not None:
                self._cooldown.pop(msg.chat.id, None)

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

        me = await client.get_me()
        own_username = me.username
        text = (msg.text or msg.caption or "").strip()
        reply_to_self = bool(msg.reply_to_message and msg.reply_to_message.from_user
                             and msg.reply_to_message.from_user.id == me.id)
        trig = detect(persona=self.p, text=text, own_username=own_username, reply_to_self=reply_to_self)
        in_private = chat_kind in (ChatKind.PRIVATE.value, ChatKind.BOT.value)

        is_operator = bool(msg.from_user and msg.from_user.id == self.s.operator_id)
        presence_excuse = None
        if presence.state.value in ("asleep", "offline"):
            if not is_operator:
                await session.commit()
                return
            from azura.constants import Presence as _P
            from azura.utils.timez import ts as _ts
            afk_reasons = [
                "в тиктоке залипла",
                "не могу уснуть, лежу в телефоне",
                "встала попить воды",
                "читаю твиттер в кровати",
                "скроллю пинтерест",
                "проснулась от кота",
                "смотрю ютуб в кровати",
            ]
            reason = self.rng.choice(afk_reasons)
            wake_until = _ts() + self.rng.randint(5 * 60, 15 * 60)
            presence = await presence_eng.set(
                _P.AFK, reason=reason, until_ts=wake_until,
            )
            presence_excuse = reason
            log.info("night dm from operator: AFK={} until={}", reason, wake_until)
            wake_delay = self.rng.uniform(6.0, 15.0)
            log.info("operator night-wake delay {:.1f}s", wake_delay)
            await asyncio.sleep(wake_delay)
        elif is_operator and presence.state.value in ("afk", "busy"):
            presence_excuse = presence.reason or presence.state.value
            wake_delay = self.rng.uniform(2.5, 8.0)
            log.info(
                "operator interrupt presence={} reason={!r} delay={:.1f}s",
                presence.state.value, presence_excuse, wake_delay,
            )
            await asyncio.sleep(wake_delay)
        if is_operator:
            from azura.mind.intent import ReplyDecision
            decision = ReplyDecision(decision="reply", score=1.0, reason="operator override")
            log.info("intent override: operator dm chat={}", msg.chat.id)
        else:
            decision = await intent_eng.decide_reply(
                chat_id=msg.chat.id,
                from_user_id=(msg.from_user.id if msg.from_user else None),
                text=text, trigger=trig, mood=mood, in_private=in_private,
            )
            log.info("intent chat={} decision={} score={:.2f} reason='{}'",
                     msg.chat.id, decision.decision, decision.score, decision.reason)

        if decision.decision in ("ignore", "later", "read_only"):
            from azura.utils.timez import ts as _ts
            reason = (decision.reason or "").lower()
            if "tired" in reason or "fatigue" in reason:
                base = self.rng.randint(15 * 60, 35 * 60)
            elif "ghost" in reason:
                base = self.rng.randint(8 * 60, 20 * 60)
            elif "didn't feel" in reason or "didnt feel" in reason or "lazy" in reason:
                base = self.rng.randint(5 * 60, 15 * 60)
            elif decision.decision == "read_only":
                base = self.rng.randint(3 * 60, 10 * 60)
            else:
                base = self.rng.randint(6 * 60, 18 * 60)
            self._cooldown[msg.chat.id] = _ts() + base
            log.info("chat {} → cooldown {}s ({} / {})",
                     msg.chat.id, base, decision.decision, decision.reason)
            if decision.decision == "read_only":
                try:
                    await client.read_chat_history(msg.chat.id)
                except Exception:
                    pass
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
            "local_time": clk.local.strftime("%H:%M"),
            "local_weekday": clk.local.strftime("%A"),
            "local_date": clk.local.strftime("%Y-%m-%d"),
            "is_sleep_window": clk.is_sleep_window,
            "is_weekend": clk.is_weekend,
            "is_forwarded": bool(getattr(msg, "forward_origin", None)),
            "avoid_recent": self.style.recent_texts(chat_id=msg.chat.id, limit=8),
            "presence_excuse": presence_excuse,
            "presence_reason": presence.reason,
            "my_chat_role": await self._fetch_my_chat_role(client, msg.chat.id, chat_kind, me.id),
        }
        if is_operator:
            op_name = (msg.from_user.first_name if msg.from_user else "друг") or "друг"
            situation["relation"] = (
                f"You are texting {op_name} — your closest, oldest friend. "
                "You trust him completely. You can be sarcastic, blunt, tired, affectionate. "
                "You can also tell him you'll do something for you (write to a person, change your bio, "
                "go AFK, etc.) and you actually DO it. He sometimes asks small chores or wants to know how you are. "
                "NEVER react to his messages with 'I'm not a bot' — he KNOWS you, he's not testing you. "
                "If he asks 'what commands can I give you' — he means casually 'what can you do for me' — "
                "answer like a friend: 'ну могу кому-то написать, отписываться тебе, менять свой профиль, спать по твоему расписанию — что хочешь'."
            )
        else:
            situation["relation"] = "a contact (not operator). normal social rules apply."
        result = await agent.run(
            mood=mood, situation=situation, user_prompt=user_prompt,
            tools=tools, max_steps=4,
        )
        if result.messages:
            await self._coalescer.mark_runner_committed(msg.chat.id)
            await sender.send(
                msg.chat.id, result.messages,
                mood=mood, clock=clk,
                in_private=in_private, urgency=urgency(trig),
                reply_to=msg.id if not in_private else None,
            )
            try:
                await client.read_chat_history(msg.chat.id)
            except Exception:
                pass
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
            async def _direct_sender(chat_id, messages, opts):
                from pyrogram.enums import ChatAction
                from azura.telegram.tg_presence import go_online_briefly
                import asyncio as _asyncio
                target = chat_id
                if isinstance(target, str) and not target.lstrip("-").isdigit():
                    target = target.lstrip("@")
                sent = 0
                last_id = None
                resolved_id: int | None = None
                msgs = [t for t in messages if t]
                total_chars = sum(len(m) for m in msgs)
                approx_secs = max(15.0, min(90.0, total_chars / 12.0 + 10.0))
                await go_online_briefly(client, seconds=approx_secs, reason=f"op.direct.chat={chat_id}")

                from azura.humanize.typing import type_with_ticks
                import random as _random

                async def _ping_typing(cid):
                    try:
                        await client.send_chat_action(cid, ChatAction.TYPING)
                    except Exception as e:
                        log.debug("send_chat_action failed chat={} err={}", cid, e)

                def _type_delay_for(text):
                    chars = len(text)
                    base = max(0.8, min(7.0, chars / 18.0))
                    return base * _random.uniform(0.75, 1.35)

                for idx, text in enumerate(msgs):
                    typing_target = resolved_id if resolved_id is not None else target
                    type_s = _type_delay_for(text)
                    log.info(
                        "typing burst chat={} chars={} secs={:.1f}",
                        typing_target, len(text), type_s,
                    )
                    await type_with_ticks(
                        chat_id=typing_target, total_seconds=type_s, keepalive=_ping_typing,
                    )
                    m = await client.send_message(target, text)
                    sent += 1
                    last_id = getattr(m, "id", None)
                    if resolved_id is None and m and getattr(m, "chat", None):
                        resolved_id = m.chat.id
                        target = resolved_id
                    if idx + 1 < len(msgs):
                        next_len = len(msgs[idx + 1])
                        gap = max(0.4, min(2.5, next_len / 70.0)) * _random.uniform(0.6, 1.5)
                        await _asyncio.sleep(gap)
                if resolved_id is not None:
                    try:
                        await client.read_chat_history(resolved_id)
                    except Exception:
                        pass
                return {"sent": sent, "skipped": 0, "last_id": last_id, "chat_id": resolved_id}

            async def _direct_sticker(chat_id, query):
                items = await memory.repos.stickers.pick_by_mood(
                    valence=0.0, arousal=0.4, limit=3,
                )
                if not items:
                    return {"ok": False, "reason": "no stickers"}
                pick = items[0]
                m = await client.send_sticker(chat_id, pick.file_id)
                await memory.repos.stickers.mark_used(pick.id)
                return {"ok": True, "msg_id": m.id}

            async def _direct_gif(chat_id, query):
                items = await memory.repos.gifs.pick_by_tags(
                    [t.strip() for t in str(query).split(",") if t.strip()], limit=3,
                )
                if not items:
                    return {"ok": False, "reason": "no gifs"}
                pick = items[0]
                msg2 = await client.send_animation(chat_id, pick.file_id)
                await memory.repos.gifs.mark_used(pick.id)
                return {"ok": True, "msg_id": msg2.id}

            async def _direct_media(chat_id, url, kind):
                return await send_url(client, chat_id, url, kind=kind)

            ctx.sender = _direct_sender
            ctx.sticker_sender = _direct_sticker
            ctx.gif_sender = _direct_gif
            ctx.media_sender = _direct_media
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
    """Attach the dispatcher to the kurigram client (message + edited + deleted + reaction + raw typing)."""
    from pyrogram.handlers import (
        DeletedMessagesHandler,
        EditedMessageHandler,
        MessageReactionHandler,
        RawUpdateHandler,
    )
    client.add_handler(MessageHandler(dispatcher.on_message, filters.all))
    client.add_handler(EditedMessageHandler(dispatcher.on_edited, filters.all))
    client.add_handler(DeletedMessagesHandler(dispatcher.on_deleted))
    try:
        client.add_handler(MessageReactionHandler(dispatcher.on_reaction))
    except Exception:
        pass
    try:
        client.add_handler(RawUpdateHandler(dispatcher.on_raw_update))
    except Exception:
        log.exception("failed to add RawUpdateHandler for typing")
