"""Attention reader: walks the chat priority queue and marks chats as read."""
from __future__ import annotations

import asyncio

from pyrogram import Client

from azura.constants import Presence
from azura.memory.service import MemoryService
from azura.mind.attention import Attention
from azura.mind.mood import MoodView
from azura.mind.presence import PresenceEngine
from azura.utils.log import get_logger
from azura.utils.rng import Rng

log = get_logger("tg.read")


class Reader:
    """Implements the priority schema: private → group → channel → muted private → muted group."""

    def __init__(
        self,
        client: Client,
        *,
        attention: Attention,
        presence: PresenceEngine,
        memory: MemoryService,
        rng: Rng,
    ) -> None:
        self.c = client
        self.attention = attention
        self.presence = presence
        self.memory = memory
        self.rng = rng

    async def cycle(self, *, mood: MoodView, max_chats: int = 6, persona=None) -> int:
        """One attention pass. Returns the number of chats actually opened."""
        cur = await self.presence.current()
        if cur.state in (Presence.ASLEEP, Presence.OFFLINE, Presence.AFK, Presence.BUSY):
            log.info("reader skip: presence={}", cur.state.value)
            return 0
        if persona is not None:
            try:
                from azura.mind.clock import snapshot
                clk = snapshot(persona)
                if clk.is_sleep_window:
                    log.info("reader skip: sleep window (clk)")
                    return 0
            except Exception:
                pass
        queue = await self.attention.queue(mood=mood, limit=max_chats)
        opened = 0
        for cand in queue:
            try:
                att = await self.memory.repos.attention.start(cand.chat_id)
                await self.c.read_chat_history(cand.chat_id)
                read = await self.memory.repos.messages.mark_seen(cand.chat_id, 10**18)
                await self.memory.repos.attention.finish(
                    att.id, msgs_read=read, decided="read",
                )
                opened += 1
                await asyncio.sleep(self.rng.uniform(1.5, 6.0))
            except Exception as e:
                log.warning("reader failed on chat {}: {}", cand.chat_id, e)
        await self.memory.repos.s.commit()
        return opened
