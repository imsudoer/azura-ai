"""Post-restart catch-up: scan all chats with unseen messages and re-evaluate.

Also used as a periodic 'pending collector' — finds chats where someone
wrote but we haven't responded, and re-submits them for processing.
"""
from __future__ import annotations

import asyncio

from pyrogram import Client
from pyrogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from azura.db.repo import Repos
from azura.memory.service import MemoryService
from azura.mind.chat_heat import chat_heat
from azura.mind.clock import snapshot
from azura.mind.intent import IntentEngine
from azura.mind.mood import MoodEngine
from azura.mind.presence import PresenceEngine
from azura.personality.schema import Persona
from azura.utils.log import get_logger
from azura.utils.rng import Rng
from azura.utils.timez import ts

log = get_logger("tg.catchup")


async def catchup_unseen(
    client: Client,
    persona: Persona,
    sm: async_sessionmaker[AsyncSession],
    rng: Rng,
    coalescer,
    *,
    max_chats: int = 15,
) -> int:
    """Scan chats with unseen messages and re-submit worthy ones to coalescer.

    Returns number of chats queued for response.
    """
    queued = 0
    async with sm() as session:
        r = Repos(session)
        m = MemoryService(r)
        chats = await r.chats.all_active()

        presence_eng = PresenceEngine(persona, m, rng=rng)
        cur = await presence_eng.current()
        if cur.state.value in ("asleep", "offline"):
            log.info("catchup skip: presence={}", cur.state.value)
            return 0

        mood_eng = MoodEngine(persona, m, rng=rng)
        mood = await mood_eng.now()
        clk = snapshot(persona)

        if clk.is_sleep_window:
            log.info("catchup skip: sleep window")
            return 0

        from azura.constants import ChatKind
        candidates = []
        for c in chats:
            if c.importance <= -100:
                continue
            unseen = await r.messages.unseen_count(c.id)
            if unseen == 0:
                continue
            heat = await chat_heat(r, c.id)
            is_private = c.kind in (ChatKind.PRIVATE.value, ChatKind.BOT.value)
            if not is_private and heat < 0.5:
                continue
            candidates.append((c, unseen, heat))

        candidates.sort(key=lambda x: (-x[2], -x[1]))

        for c, unseen, heat in candidates[:max_chats]:
            last = await r.archive.last_incoming_ts(c.id)
            if not last:
                continue
            age = ts() - last
            if age > 3600:
                log.debug("catchup skip chat={} age={}s (stale)", c.id, age)
                continue

            last_self = await r.archive.last_self_ts(c.id)
            if last_self and last_self > last:
                log.debug("catchup skip chat={} (we replied after them)", c.id)
                continue

            log.info(
                "catchup candidate chat={} unseen={} heat={:.2f} age={}s kind={}",
                c.id, unseen, heat, age, c.kind,
            )

            try:
                latest = None
                async for m_msg in client.get_chat_history(c.id, limit=1):
                    latest = m_msg
                    break
                if latest and not latest.outgoing:
                    await coalescer.submit(c.id, latest)
                    queued += 1
                    log.info("catchup QUEUED chat={} msg_id={}", c.id, latest.id)
                elif latest:
                    log.debug("catchup skip chat={} (last msg is outgoing)", c.id)
            except Exception:
                log.exception("catchup fetch failed chat={}", c.id)

    return queued


async def periodic_catchup(
    client: Client,
    persona: Persona,
    sm: async_sessionmaker[AsyncSession],
    rng: Rng,
    coalescer,
    stop_event: asyncio.Event,
    interval_s: float = 120.0,
):
    """Run catchup_unseen periodically as a background task."""
    await asyncio.sleep(30.0)
    while not stop_event.is_set():
        try:
            n = await catchup_unseen(client, persona, sm, rng, coalescer)
            if n > 0:
                log.info("periodic catchup: queued {} chats", n)
        except Exception:
            log.exception("periodic catchup failed")
        jitter = rng.uniform(0.7, 1.3)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s * jitter)
            break
        except asyncio.TimeoutError:
            pass
