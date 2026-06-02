"""Background loop that periodically runs the attention reader."""
from __future__ import annotations

import asyncio

from pyrogram import Client
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from azura.db.repo import Repos
from azura.memory.service import MemoryService
from azura.mind.attention import Attention
from azura.mind.mood import MoodEngine
from azura.mind.presence import PresenceEngine
from azura.personality.schema import Persona
from azura.telegram.readers import Reader
from azura.utils.log import get_logger
from azura.utils.rng import Rng

log = get_logger("tg.reader_loop")


class ReaderLoop:
    """Periodic attention-reader runner."""

    def __init__(
        self,
        *,
        client: Client,
        persona: Persona,
        sessionmaker: async_sessionmaker[AsyncSession],
        rng: Rng,
        period_s: float = 90.0,
    ) -> None:
        self.c = client
        self.p = persona
        self.sm = sessionmaker
        self.rng = rng
        self.period = period_s
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="reader_loop")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await self._tick()
                except Exception:
                    log.exception("reader tick failed")
                delay = self.rng.jitter(self.period, 0.4)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                    return
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def _tick(self) -> None:
        async with self.sm() as s:
            r = Repos(s); m = MemoryService(r)
            mood = MoodEngine(self.p, m, rng=self.rng)
            presence = PresenceEngine(self.p, m, rng=self.rng)
            att = Attention(self.p, r, m)
            reader = Reader(self.c, attention=att, presence=presence, memory=m, rng=self.rng)
            mv = await mood.now()
            opened = await reader.cycle(mood=mv, max_chats=self.rng.randint(3, 7))
            await s.commit()
            if opened:
                log.info("attention pass: opened {} chats", opened)
