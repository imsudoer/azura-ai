"""Presence engine: asleep / offline / afk / online / busy with reasons."""
from __future__ import annotations

from dataclasses import dataclass

from azura.constants import Presence
from azura.memory.service import MemoryService
from azura.mind.clock import ClockSnapshot, seconds_until_wake
from azura.personality.schema import Persona
from azura.utils.rng import Rng
from azura.utils.timez import ts


@dataclass
class PresenceView:
    """Frozen presence state for callers."""
    state: Presence
    reason: str | None
    until_ts: int | None
    started_ts: int

    @property
    def is_reachable(self) -> bool:
        return self.state in (Presence.ONLINE, Presence.BUSY)


class PresenceEngine:
    """Decide and persist presence transitions."""

    def __init__(
        self, persona: Persona, memory: MemoryService, *, rng: Rng, tg_client=None,
    ) -> None:
        self.p = persona
        self.m = memory
        self.rng = rng
        self.tg = tg_client

    async def current(self) -> PresenceView:
        cur = await self.m.repos.presence.current()
        if cur is None:
            await self.set(Presence.OFFLINE, reason="cold start")
            cur = await self.m.repos.presence.current()
        assert cur is not None
        return PresenceView(
            state=Presence(cur.state), reason=cur.reason,
            until_ts=cur.until_ts, started_ts=cur.started_ts,
        )

    async def set(
        self,
        state: Presence,
        *,
        reason: str | None = None,
        until_ts: int | None = None,
        journal: bool = True,
    ) -> PresenceView:
        await self.m.repos.presence.push(state.value, reason=reason, until_ts=until_ts)
        if journal:
            await self.m.repos.journal.write(
                f"→ {state.value}" + (f" ({reason})" if reason else ""),
                kind="presence",
            )

        cur = await self.m.repos.presence.current()
        assert cur is not None
        return PresenceView(
            state=Presence(cur.state), reason=cur.reason,
            until_ts=cur.until_ts, started_ts=cur.started_ts,
        )

    async def tick(self, *, clock: ClockSnapshot, fatigue: float) -> PresenceView:
        """Auto-transition based on clock + random wakeup chance."""
        cur = await self.current()
        now = ts()
        if cur.until_ts and now >= cur.until_ts and cur.state in (Presence.AFK, Presence.BUSY):
            if clock.is_sleep_window:
                until = ts() + seconds_until_wake(self.p, clock.local)
                await self.set(Presence.ASLEEP, reason="обратно спать", until_ts=until)
            else:
                await self.set(Presence.ONLINE, reason="back")
            cur = await self.current()
        if clock.is_sleep_window:
            if cur.state == Presence.ASLEEP:
                if self.rng.chance(self._wake_chance(fatigue)):
                    until = now + self.rng.randint(5 * 60, 15 * 60)
                    return await self.set(
                        Presence.AFK, reason="проснулась ночью", until_ts=until
                    )
                return cur
            if cur.state == Presence.AFK:
                return cur
            until = ts() + seconds_until_wake(self.p, clock.local)
            return await self.set(Presence.ASLEEP, reason="going to sleep", until_ts=until)
        if cur.state == Presence.ASLEEP:
            return await self.set(Presence.ONLINE, reason="woke up")
        if clock.is_work_window and cur.state == Presence.ONLINE:
            if self.rng.chance(0.4 * self.p.traits.get("conscientiousness", 0.5)):
                return await self.set(Presence.BUSY, reason="work block")
        if cur.state == Presence.BUSY and not clock.is_work_window:
            return await self.set(Presence.ONLINE, reason="work over")
        return cur

    def _wake_chance(self, fatigue: float) -> float:
        """Chance of a brief night wakeup, lower when sleep-deprived."""
        base = 0.03
        t = self.p.traits
        owl = 0.04 if self.p.rhythm.night_owl else 0.0
        impulse = t.get("impulsivity", 0.5) * 0.05
        light_sleeper = (1 - fatigue) * 0.04
        return min(0.25, base + owl + impulse + light_sleeper)

    async def go_afk(self, minutes: int, reason: str) -> PresenceView:
        until = ts() + minutes * 60
        return await self.set(Presence.AFK, reason=reason, until_ts=until)

    async def come_back(self) -> PresenceView:
        return await self.set(Presence.ONLINE, reason="back")
