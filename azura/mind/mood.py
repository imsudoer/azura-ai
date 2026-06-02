"""Mood engine: drift, event nudges, baseline pull, time-of-day modifiers."""
from __future__ import annotations

import math
from dataclasses import dataclass

from azura.db.models import MoodState
from azura.memory.service import MemoryService
from azura.mind.clock import ClockSnapshot
from azura.personality.schema import Persona
from azura.utils.rng import Rng
from azura.utils.timez import ts


@dataclass
class MoodView:
    """Snapshot of mood used by every other subsystem."""
    valence: float
    arousal: float
    energy: float
    focus: float
    stress: float
    fatigue: float


def as_view(m: MoodState) -> MoodView:
    return MoodView(
        valence=m.valence, arousal=m.arousal, energy=m.energy,
        focus=m.focus, stress=m.stress, fatigue=m.fatigue,
    )


def baseline_for(persona: Persona) -> MoodView:
    """Trait-derived resting mood the persona drifts toward."""
    t = persona.traits
    val = (t["agreeableness"] - t["neuroticism"]) * 0.6
    aro = 0.3 + t["extraversion"] * 0.3 + t["impulsivity"] * 0.2
    en = 0.5 + (t["extraversion"] - t["neuroticism"]) * 0.2
    fo = 0.5 + (t["conscientiousness"] - 0.5) * 0.4
    stress = 0.2 + t["neuroticism"] * 0.4
    fat = 0.2
    return MoodView(
        valence=_c(val, -1, 1), arousal=_c(aro), energy=_c(en),
        focus=_c(fo), stress=_c(stress), fatigue=_c(fat),
    )


def _c(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class MoodEngine:
    """Drift mood toward baseline, apply event nudges, adjust by clock and fatigue."""

    def __init__(self, persona: Persona, memory: MemoryService, *, rng: Rng) -> None:
        self.p = persona
        self.m = memory
        self.rng = rng
        self.base = baseline_for(persona)

    async def drift(self, *, dt_minutes: float, clock: ClockSnapshot) -> MoodView:
        """Pull mood toward baseline; layer time-of-day and random events."""
        cur = as_view(await self.m.repos.mood.get())
        pull = 1 - math.exp(-dt_minutes / 90.0)
        val = cur.valence + (self.base.valence - cur.valence) * pull
        aro = cur.arousal + (self.base.arousal - cur.arousal) * pull
        en = cur.energy + (self.base.energy - cur.energy) * pull
        fo = cur.focus + (self.base.focus - cur.focus) * pull
        st = cur.stress + (self.base.stress - cur.stress) * pull
        fa = cur.fatigue + (self.base.fatigue - cur.fatigue) * pull

        phase = clock.phase
        if phase in ("deep_night", "night"):
            en -= 0.10
            fa += 0.08
            fo -= 0.05
        elif phase in ("morning", "early_morning"):
            en += 0.05
            fo += 0.05
        elif phase == "evening":
            aro += 0.04

        if clock.is_work_window:
            fo += 0.05
            fa += 0.02
        if clock.is_weekend:
            st -= 0.05

        if self.rng.chance(0.04):
            val += self.rng.gauss(0, 0.08)
            aro += self.rng.gauss(0, 0.06)

        out = MoodView(
            valence=_c(val, -1, 1), arousal=_c(aro), energy=_c(en),
            focus=_c(fo), stress=_c(stress := st), fatigue=_c(fa),
        )
        await self.m.repos.mood.set(
            valence=out.valence, arousal=out.arousal, energy=out.energy,
            focus=out.focus, stress=out.stress, fatigue=out.fatigue,
        )
        return out

    async def nudge(self, *, valence: float = 0.0, arousal: float = 0.0, stress: float = 0.0, note: str | None = None) -> MoodView:
        """Apply an immediate emotional event."""
        cur = as_view(await self.m.repos.mood.get())
        out = MoodView(
            valence=_c(cur.valence + valence, -1, 1),
            arousal=_c(cur.arousal + arousal),
            energy=_c(cur.energy - abs(arousal) * 0.05),
            focus=cur.focus,
            stress=_c(cur.stress + stress),
            fatigue=cur.fatigue,
        )
        await self.m.repos.mood.set(
            valence=out.valence, arousal=out.arousal, energy=out.energy,
            focus=out.focus, stress=out.stress, fatigue=out.fatigue, note=note,
        )
        return out

    async def add_fatigue(self, delta: float) -> None:
        cur = await self.m.repos.mood.get()
        await self.m.repos.mood.set(fatigue=_c(cur.fatigue + delta))

    async def sleep_reset(self) -> None:
        """Morning reset: low fatigue, mood pulled toward baseline."""
        await self.m.repos.mood.set(
            fatigue=0.15, stress=_c(self.base.stress - 0.05),
            valence=self.base.valence, energy=_c(self.base.energy + 0.1),
            note="woke up",
        )

    async def now(self) -> MoodView:
        return as_view(await self.m.repos.mood.get())

    async def journal_if_significant(self) -> None:
        """Write a journal line when mood shifts a lot from baseline."""
        cur = await self.now()
        if abs(cur.valence - self.base.valence) > 0.4 or cur.stress > 0.75:
            await self.m.repos.journal.write(
                f"mood shift: v={cur.valence:+.2f}, stress={cur.stress:.2f}",
                kind="mood",
            )


def _ts() -> int:
    return ts()
