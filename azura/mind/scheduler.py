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
        tg_client=None,
        on_tail: Callable[[int, str], Awaitable[None]] | None = None,
        on_status: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.p = persona
        self.sm = sessionmaker
        self.rng = rng
        self.tails = tails
        self.tg_client = tg_client
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
            LoopSpec("self_initiate", self._self_initiate_tick, 10 * 60.0, 0.5),
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
        from azura.utils.timez import ts as _ts
        from azura.constants import Presence as _P
        async with self.sm() as s:
            r = Repos(s); m = MemoryService(r)
            presence = PresenceEngine(self.p, m, rng=self.rng)
            cur = await presence.current()
            now = _ts()

            if cur.state.value == "online":
                last_self = await r.archive.last_self_ts() if hasattr(r.archive, "last_self_ts") else None
                if last_self and (now - last_self) > 15 * 60 and self.rng.chance(0.25):
                    reasons = [
                        "вышла скроллить тикток",
                        "села пить чай",
                        "открыла фигму",
                        "пошла на кухню",
                        "в яндекс-музыке залипла",
                        "в пинтересте сижу",
                        "погулять вышла",
                        "читаю книгу",
                        "смотрю ютуб",
                        "рисую в прокреате",
                    ]
                    minutes = self.rng.randint(10, 45)
                    reason = self.rng.choice(reasons)
                    await presence.set(_P.AFK, reason=reason, until_ts=now + minutes * 60)
                    log.info("life: drift online -> afk ({}, {} min)", reason, minutes)

            elif cur.state.value == "afk":
                if cur.until_ts and now >= cur.until_ts:
                    await presence.set(_P.ONLINE, reason="back")
                    log.info("life: afk expired -> online")

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
        from azura.config import get_settings
        from azura.telegram.media_cache import enforce_cache_quota
        async with self.sm() as s:
            r = Repos(s); m = MemoryService(r)
            stats = await m.forgetting.step()
        try:
            enforce_cache_quota(max_mb=get_settings().media_cache_max_mb)
        except Exception:
            log.exception("media cache eviction failed")
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

    async def _self_initiate_tick(self) -> None:
        """Periodically check if she wants to write to someone first."""
        if self.tg_client is None:
            return
        async with self.sm() as s:
            r = Repos(s); m = MemoryService(r)
            presence = PresenceEngine(self.p, m, rng=self.rng)
            cur = await presence.current()
            if cur.state.value in ("asleep", "offline"):
                return

            mood_eng = MoodEngine(self.p, m, rng=self.rng)
            mood = await mood_eng.now()
            clk = snapshot(self.p)
            if clk.is_sleep_window:
                return

            from azura.mind.intent import IntentEngine
            from azura.db.repo.archive import ArchiveRepo
            from azura.utils.timez import ts as _ts
            intent = IntentEngine(self.p, m, rng=self.rng)
            now = _ts()

            candidates = await m.repos.opinions.close_contacts()
            if not candidates:
                return

            self.rng.shuffle(candidates)

            for peer_id in candidates[:5]:
                last_self = await m.repos.archive.last_self_ts(peer_id)
                age = (now - last_self) if last_self else 7 * 86400
                dec = await intent.decide_first_message(
                    peer_id=peer_id,
                    last_contact_age_s=age,
                    mood=mood,
                    clock_evening=clk.phase in ("late_evening", "night"),
                )
                log.info(
                    "self_initiate peer={} decision={} score={:.2f} reason={!r}",
                    peer_id, dec.decision, dec.score, dec.reason,
                )
                if dec.decision != "reply":
                    continue

                try:
                    await self._send_first_message(peer_id, m, mood, clk)
                except Exception:
                    log.exception("self_initiate send failed peer={}", peer_id)
                break

            await s.commit()

    async def _send_first_message(self, peer_id: int, m, mood, clk) -> None:
        from azura.mind.agent import Agent
        from azura.llm.templates import render

        user_row = await m.repos.users.get(peer_id)
        name = "человек"
        if user_row:
            name = user_row.first_name or user_row.username or str(peer_id)

        prox = await m.opinions.proximity(peer_id)
        op = await m.opinions.user(peer_id)
        feelings = await m.feelings.toward_user(peer_id)

        recent = await m.repos.archive.recent(peer_id, limit=8)
        recent_lines = []
        for row in recent[-8:]:
            who = "me" if row.is_self else name
            txt = (row.text or row.caption or "")[:200]
            if txt:
                recent_lines.append(f"{who}: {txt}")

        situation = {
            "local_time": clk.local.strftime("%H:%M"),
            "clock_phase": clk.phase,
            "target_name": name,
            "proximity": prox.value,
            "opinion": op,
            "feelings": {k: round(v, 2) for k, v in feelings.items()},
            "recent_exchange": "\n".join(recent_lines[-6:]) if recent_lines else "no recent messages",
        }

        agent = Agent(self.p, m)
        system = render(
            "self_initiate.j2",
            persona=self.p,
            situation=situation,
        )
        result = await agent.run(
            mood=mood,
            situation=situation,
            user_prompt=system,
            tools=[],
            max_steps=1,
        )
        if not result.messages:
            log.info("self_initiate: agent returned no messages for peer={}", peer_id)
            return

        from azura.telegram.senders import Sender
        from azura.telegram.tg_presence import go_online_briefly
        from azura.humanize.style_diversity import StyleDiversity
        await go_online_briefly(self.tg_client, seconds=30.0, reason=f"self_initiate.peer={peer_id}")
        sender = Sender(
            self.tg_client, persona=self.p, memory=m, rng=self.rng,
            backpressure=None, style=StyleDiversity(window=20, n=4),
        )
        await sender.send(
            peer_id, result.messages,
            mood=mood, clock=clk,
            in_private=True, urgency=0.0,
        )
        log.info(
            "self_initiate SENT peer={} name={!r} msgs={}",
            peer_id, name, len(result.messages),
        )
