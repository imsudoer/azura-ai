"""Global memory: persona-wide facts not tied to any chat."""
from __future__ import annotations

from azura.constants import MemoryKind
from azura.db.repo import Repos


class GlobalMemory:
    """'Things about me' / 'things about my life' — not chat-scoped."""

    def __init__(self, repos: Repos) -> None:
        self.r = repos

    async def add(
        self,
        content: str,
        *,
        topic: str | None = None,
        importance: float = 0.7,
        confidence: float = 0.9,
        embedding: list[float] | None = None,
    ) -> int:
        m = await self.r.memory.add(
            kind=MemoryKind.GLOBAL.value,
            content=content,
            topic=topic,
            importance=importance,
            confidence=confidence,
            embedding=embedding,
        )
        return m.id

    async def all(self, limit: int = 100) -> list[str]:
        items = await self.r.memory.recent(MemoryKind.GLOBAL.value, limit=limit)
        return [it.content for it in items]

    async def search(self, query: str, *, limit: int = 8) -> list[str]:
        items = await self.r.memory.search_text(query, limit=limit, kind=MemoryKind.GLOBAL.value)
        return [it.content for it in items]
