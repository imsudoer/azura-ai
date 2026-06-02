"""Mood state repository (single-row snapshot)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import MoodState
from azura.utils.timez import ts


class MoodRepo:
    """Persist the persona's current mood snapshot."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def get(self) -> MoodState:
        r = await self.s.execute(select(MoodState).where(MoodState.id == 1))
        m = r.scalar_one_or_none()
        if m is None:
            m = MoodState(id=1, updated_ts=ts())
            self.s.add(m)
            await self.s.flush()
        return m

    async def set(
        self,
        *,
        valence: float | None = None,
        arousal: float | None = None,
        energy: float | None = None,
        focus: float | None = None,
        stress: float | None = None,
        fatigue: float | None = None,
        note: str | None = None,
    ) -> MoodState:
        m = await self.get()
        if valence is not None:
            m.valence = max(-1.0, min(1.0, valence))
        if arousal is not None:
            m.arousal = max(0.0, min(1.0, arousal))
        if energy is not None:
            m.energy = max(0.0, min(1.0, energy))
        if focus is not None:
            m.focus = max(0.0, min(1.0, focus))
        if stress is not None:
            m.stress = max(0.0, min(1.0, stress))
        if fatigue is not None:
            m.fatigue = max(0.0, min(1.0, fatigue))
        if note is not None:
            m.note = note
        m.updated_ts = ts()
        await self.s.flush()
        return m
