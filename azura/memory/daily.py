"""Daily memory: today's situational notes, wiped at sleep."""
from __future__ import annotations

from azura.constants import MemoryKind
from azura.db.repo import Repos


class DailyMemory:
    """'Today I planned X, today I felt Y' — cleared on sleep cycle."""

    def __init__(self, repos: Repos) -> None:
        self.r = repos

    async def add(self, content: str, *, topic: str | None = None) -> int:
        m = await self.r.memory.add(
            kind=MemoryKind.DAILY.value, content=content, topic=topic, importance=0.5
        )
        return m.id

    async def list(self, limit: int = 50) -> list[str]:
        items = await self.r.memory.recent(MemoryKind.DAILY.value, limit=limit)
        return [it.content for it in items]

    async def wipe(self) -> int:
        """Drop all daily entries — called at the end of the day."""
        items = await self.r.memory.recent(MemoryKind.DAILY.value, limit=10_000)
        for it in items:
            await self.r.s.delete(it)
        await self.r.s.flush()
        return len(items)
