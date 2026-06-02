"""Long-term memory: consolidated facts per chat or about a user."""
from __future__ import annotations

from azura.constants import MemoryKind
from azura.db.repo import Repos


class LongTerm:
    """Stable facts the persona has decided to keep. Smaller volume, higher confidence."""

    def __init__(self, repos: Repos) -> None:
        self.r = repos

    async def add_fact(
        self,
        content: str,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        topic: str | None = None,
        confidence: float = 0.8,
        importance: float = 0.6,
        embedding: list[float] | None = None,
    ) -> int:
        m = await self.r.memory.add(
            kind=MemoryKind.LONG.value,
            content=content,
            chat_id=chat_id,
            user_id=user_id,
            topic=topic,
            confidence=confidence,
            importance=importance,
            embedding=embedding,
        )
        return m.id

    async def for_chat(self, chat_id: int, limit: int = 30) -> list[str]:
        items = await self.r.memory.recent(MemoryKind.LONG.value, chat_id=chat_id, limit=limit)
        return [it.content for it in items]

    async def search(self, query: str, *, limit: int = 8) -> list[str]:
        items = await self.r.memory.search_text(query, limit=limit, kind=MemoryKind.LONG.value)
        return [it.content for it in items]

    async def search_vec(self, embedding: list[float], *, k: int = 8) -> list[str]:
        items = await self.r.memory.search_vec(embedding, k=k, kind=MemoryKind.LONG.value)
        return [it.content for it, _ in items]
