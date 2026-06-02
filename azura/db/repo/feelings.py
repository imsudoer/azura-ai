"""Feelings repository — emotional states toward targets, with time-decay."""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import Feeling
from azura.utils.timez import ts


class FeelingsRepo:
    """Persist time-decaying feelings keyed by (target, emotion)."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def get(self, target_kind: str, target_id: int, emotion: str) -> Feeling | None:
        r = await self.s.execute(
            select(Feeling).where(
                Feeling.target_kind == target_kind,
                Feeling.target_id == target_id,
                Feeling.emotion == emotion,
            )
        )
        return r.scalar_one_or_none()

    async def bump(
        self,
        target_kind: str,
        target_id: int,
        emotion: str,
        *,
        delta: float = 0.1,
        decay_rate: float = 0.05,
        reason: str | None = None,
    ) -> Feeling:
        """Add intensity to an emotion, creating the row if needed."""
        f = await self.get(target_kind, target_id, emotion)
        now = ts()
        if f is None:
            f = Feeling(
                target_kind=target_kind,
                target_id=target_id,
                emotion=emotion,
                intensity=max(0.0, min(1.0, delta)),
                decay_rate=decay_rate,
                reason=reason,
                started_ts=now,
                updated_ts=now,
            )
            self.s.add(f)
        else:
            f.intensity = max(0.0, min(1.0, f.intensity + delta))
            f.decay_rate = decay_rate
            if reason:
                f.reason = reason
            f.updated_ts = now
        await self.s.flush()
        return f

    async def list_for(self, target_kind: str, target_id: int) -> list[Feeling]:
        r = await self.s.execute(
            select(Feeling).where(
                Feeling.target_kind == target_kind, Feeling.target_id == target_id
            )
        )
        return list(r.scalars().all())

    async def decay_step(self, now: int | None = None) -> int:
        """Apply exponential decay to all feelings; delete those falling below 0.02."""
        now = now or ts()
        r = await self.s.execute(select(Feeling))
        items = list(r.scalars().all())
        removed = 0
        for f in items:
            dt = max(0, now - (f.updated_ts or now))
            if dt <= 0:
                continue
            hours = dt / 3600.0
            f.intensity = f.intensity * math.exp(-f.decay_rate * hours)
            if f.intensity < 0.02:
                await self.s.delete(f)
                removed += 1
            f.updated_ts = now
        await self.s.flush()
        return removed
