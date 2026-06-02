"""Forgetting: decay accumulation, eviction of unused/unimportant memory."""
from __future__ import annotations

import math

from sqlalchemy import select

from azura.constants import MemoryKind
from azura.db.models import MemoryItem
from azura.db.repo import Repos
from azura.utils.timez import ts


class Forgetting:
    """Apply decay over time; delete items whose decay exceeded their importance."""

    def __init__(self, repos: Repos) -> None:
        self.r = repos

    async def step(
        self,
        *,
        half_life_hours: dict[str, float] | None = None,
    ) -> dict[str, int]:
        """One forgetting pass across memory tiers."""
        hl = half_life_hours or {
            MemoryKind.SHORT.value: 6,
            MemoryKind.DAILY.value: 18,
            MemoryKind.LONG.value: 24 * 30,
            MemoryKind.EPISODIC.value: 24 * 90,
            MemoryKind.GLOBAL.value: 24 * 365,
        }
        now = ts()
        stats: dict[str, int] = {"updated": 0, "removed": 0}
        rows = await self.r.s.execute(select(MemoryItem))
        items = list(rows.scalars().all())
        for it in items:
            half = hl.get(it.kind, 24 * 7)
            dt_h = max(0.0, (now - it.ts) / 3600.0)
            recency_boost = 1.0
            if it.last_used_ts and now - it.last_used_ts < 3 * 24 * 3600:
                recency_boost = 0.4
            decay = 1 - math.exp(-math.log(2) * dt_h * recency_boost / half)
            it.decay = max(it.decay, decay)
            threshold = 0.7 + 0.3 * it.importance + 0.05 * min(it.use_count, 20)
            if it.decay >= threshold and it.kind in (MemoryKind.SHORT.value, MemoryKind.DAILY.value):
                await self.r.s.delete(it)
                stats["removed"] += 1
            else:
                stats["updated"] += 1
        await self.r.s.flush()
        await self.r.feelings.decay_step(now=now)
        return stats
