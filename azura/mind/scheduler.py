"""Asyncio scheduler running the mind's background loops with per-tick sessions."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from azura.db.repo import Repos
from azura.memory.consolidator import Consolidator
from azura.memory.dreams import Dreams
from azura.memory.service import MemoryService
from azura.mind.clock import snapshot
from azura.mind.life_events import LifeEventEngine
from azura.mind.mood import MoodEngine
from azura.mind.presence import PresenceEngine
from azura.mind.tails import TailQueue
from azura.personality.schema import Persona
from azura.utils.log import get_logger
from azura.utils.rng import Rng

log = get_logger("mind.scheduler")


@dataclass
class LoopSpec:
    """A single background loop description."""
    name: str
    fn: Callable[[], Awaitable[None]]
    period_s: float
    jitter: float = 0.2


class MindScheduler:
    """Run heartbeat, life events, tail delivery, forgetting, consolidation, dreams.

    Each loop opens its own AsyncSession via the supplied sessionmaker to avoid
    holding a long-living session for the entire process lifetime.
    """

    def __init__(
        self,
        *,
        persona: Persona,
        sessionmaker: async_sessionmaker[AsyncSession],
        rng: Rng,
        tails: TailQueue,
        on_tail: Callable[[int, str], Awaitable[None]] | None = None,
        on_status: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.p = persona
        self.sm = sessionmaker
        self.rng = rng
        self.tails = tails
        self.on_tail = on_tail
        self.on_status = on_status
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    def _loops(self) -> list[LoopSpec]:
        return [
            LoopSpec("heartbeat", self._heartbeat, 60.0, 0.3),
            LoopSpec("life_events", self._life_tick, 180.0, 0.5),
            LoopSpec("tails", self._tails_tick, 30.0, 0.3),
            LoopSpec("forgetting", self._forgetting_tick, 6 * 3600.0, 0.2),
            LoopSpec("consolidate", self._consolidate_tick, 60 * 60.0, 0.3),
            LoopSpec("dream", self._dream_tick, 15 * 60.0, 0.3),
        ]

    async def start(self) -> None:
        for loop in self._loops():
            self._tasks.append(asyncio.create_task(self._run_loop(loop), name=loop.name))
        log.info("mind scheduler started with {} loops", len(self._tasks))

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()

    async def _run_loop(self, spec: LoopSpec) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await spec.fn()
                except Exception:
                    log.exception("{} loop iteration failed", spec.name)
                delay = self.rng.jitter(spec.period_s, spec.jitter)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                    return
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def _heartbeat(self) -> None:
        async with self.sm() as s:
            r = Repos(s); m = MemoryService(r)
            mood = MoodEngine(self.p, m, rng=self.rng)
            presence = PresenceEngine(self.p, m, rng=self.rng)
            clk = snapshot(self.p)
            mv = await mood.drift(dt_minutes=1.0, clock=clk)
            pv = await presence.tick(clock=clk, fatigue=mv.fatigue)
            await mood.journal_if_significant()
            await s.commit()
        if self.on_status is not None:
            try:
                await self.on_status(pv.state.value)
            except Exception:
                log.exception("on_status failed")

    async def _life_tick(self) -> None:
        async with self.sm() as s:
            r = Repos(s); m = MemoryService(r)
            presence = PresenceEngine(self.p, m, rng=self.rng)
            cur = await presence.current()
            if cur.state.value != "online":
                return
            life = LifeEventEngine(self.p, m, presence, rng=self.rng)
            await life.maybe_roll()
            await s.commit()

    async def _tails_tick(self) -> None:
        due = self.tails.due()
        if not due:
            return
        if self.on_tail is None:
            return
        for t in due:
            try:
                await self.on_tail(t.chat_id, t.text)
            except Exception:
                log.exception("tail delivery failed for chat {}", t.chat_id)

    async def _forgetting_tick(self) -> None:
        async with self.sm() as s:
            r = Repos(s); m = MemoryService(r)
            stats = await m.forgetting.step()
            await s.commit()
            log.info("forgetting: {}", stats)

    async def _consolidate_tick(self) -> None:
        async with self.sm() as s:
            r = Repos(s); m = MemoryService(r)
            cons = Consolidator(self.p, m)
            stats = await cons.consolidate_all_active()
            await s.commit()
            log.info("consolidate: {}", stats)

    async def _dream_tick(self) -> None:
        async with self.sm() as s:
            r = Repos(s); m = MemoryService(r)
            presence = PresenceEngine(self.p, m, rng=self.rng)
            cur = await presence.current()
            if cur.state.value != "asleep":
                return
            mood = MoodEngine(self.p, m, rng=self.rng)
            dreams = Dreams(self.p, m, mood)
            stats = await dreams.run()
            log.info("dream: {}", stats)
