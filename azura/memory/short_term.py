"""Short-term memory: recent observations per chat, kept tight with TTL trim."""
from __future__ import annotations

from azura.constants import MemoryKind
from azura.db.repo import Repos
from azura.utils.timez import ts


class ShortTerm:
    """Rolling per-chat short-term notes, with caller-supplied embeddings."""

    def __init__(self, repos: Repos, *, ttl_seconds: int = 6 * 3600, keep_per_chat: int = 40) -> None:
        self.r = repos
        self.ttl = ttl_seconds
        self.keep = keep_per_chat

    async def add(
        self,
        chat_id: int,
        content: str,
        *,
        topic: str | None = None,
        user_id: int | None = None,
        importance: float = 0.4,
        embedding: list[float] | None = None,
    ) -> int:
        m = await self.r.memory.add(
            kind=MemoryKind.SHORT.value,
            content=content,
            chat_id=chat_id,
            user_id=user_id,
            topic=topic,
            importance=importance,
            embedding=embedding,
        )
        return m.id

    async def recent(self, chat_id: int, limit: int | None = None) -> list[str]:
        items = await self.r.memory.recent(
            MemoryKind.SHORT.value, chat_id=chat_id, limit=limit or self.keep
        )
        return [it.content for it in items]

    async def search(self, chat_id: int, query: str, limit: int = 5) -> list[str]:
        items = await self.r.memory.search_text(query, limit=limit, kind=MemoryKind.SHORT.value)
        return [it.content for it in items if it.chat_id == chat_id]

    async def evict_stale(self) -> int:
        """Drop entries older than ttl_seconds across all chats."""
        cutoff = ts() - self.ttl
        items = await self.r.memory.recent(MemoryKind.SHORT.value, limit=10_000)
        gone = 0
        for it in items:
            if it.ts < cutoff:
                await self.r.s.delete(it)
                gone += 1
        await self.r.s.flush()
        return gone
