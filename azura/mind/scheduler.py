"""Asyncio scheduler running the mind's background loops."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

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
    """Run mood drift, presence ticks, life events, tail delivery and consolidation jobs."""

    def __init__(
        self,
        *,
        persona: Persona,
        memory: MemoryService,
        mood: MoodEngine,
        presence: PresenceEngine,
        life: LifeEventEngine,
        tails: TailQueue,
        rng: Rng,
        on_tail: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> None:
        self.p = persona
        self.m = memory
        self.mood = mood
        self.presence = presence
        self.life = life
        self.tails = tails
        self.rng = rng
        self.on_tail = on_tail
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    def _loops(self) -> list[LoopSpec]:
        return [
            LoopSpec("heartbeat", self._heartbeat, 60.0, 0.3),
            LoopSpec("life_events", self._life_tick, 180.0, 0.5),
            LoopSpec("tails", self._tails_tick, 30.0, 0.3),
            LoopSpec("forgetting", self._forgetting_tick, 6 * 3600.0, 0.2),
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
        clk = snapshot(self.p)
        mood = await self.mood.drift(dt_minutes=1.0, clock=clk)
        await self.presence.tick(clock=clk, fatigue=mood.fatigue)
        await self.mood.journal_if_significant()

    async def _life_tick(self) -> None:
        cur = await self.presence.current()
        if cur.state.value not in ("online",):
            return
        await self.life.maybe_roll()

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
        stats = await self.m.forgetting.step()
        log.info("forgetting: {}", stats)
