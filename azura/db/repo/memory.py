"""Memory repository spanning short/long/global/daily tiers."""
from __future__ import annotations

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.fts import fts_insert_memory, fts_search_memory
from azura.db.models import MemoryItem
from azura.db.vec import vec_insert, vec_knn, vec_update
from azura.utils.timez import ts


class MemoryRepo:
    """CRUD over MemoryItem with FTS5 and sqlite-vec dual-index."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def add(
        self,
        *,
        kind: str,
        content: str,
        chat_id: int | None = None,
        user_id: int | None = None,
        topic: str | None = None,
        confidence: float = 0.7,
        importance: float = 0.5,
        embedding: list[float] | None = None,
        meta: dict | None = None,
    ) -> MemoryItem:
        """Persist a memory item; index it into FTS and vec when possible."""
        m = MemoryItem(
            kind=kind,
            chat_id=chat_id,
            user_id=user_id,
            topic=topic,
            content=content,
            confidence=confidence,
            importance=importance,
            ts=ts(),
            meta=meta or {},
        )
        self.s.add(m)
        await self.s.flush()
        conn = await self.s.connection()
        await fts_insert_memory(conn, m.id, content, topic)
        if embedding is not None:
            m.embed_id = await vec_insert(conn, "memory_vec", embedding)
            await self.s.flush()
        return m

    async def update_embedding(self, mem_id: int, embedding: list[float]) -> None:
        m = await self.s.get(MemoryItem, mem_id)
        if m is None:
            return
        conn = await self.s.connection()
        if m.embed_id is None:
            m.embed_id = await vec_insert(conn, "memory_vec", embedding)
        else:
            await vec_update(conn, "memory_vec", m.embed_id, embedding)
        await self.s.flush()

    async def touch(self, mem_id: int) -> None:
        m = await self.s.get(MemoryItem, mem_id)
        if m is None:
            return
        m.last_used_ts = ts()
        m.use_count += 1
        await self.s.flush()

    async def search_text(
        self, query: str, limit: int = 10, kind: str | None = None
    ) -> list[MemoryItem]:
        conn = await self.s.connection()
        ids = await fts_search_memory(conn, query, limit=limit * 2)
        if not ids:
            return []
        q = select(MemoryItem).where(MemoryItem.id.in_(ids))
        if kind is not None:
            q = q.where(MemoryItem.kind == kind)
        r = await self.s.execute(q)
        items = {it.id: it for it in r.scalars().all()}
        return [items[i] for i in ids if i in items][:limit]

    async def search_vec(
        self, embedding: list[float], k: int = 8, kind: str | None = None
    ) -> list[tuple[MemoryItem, float]]:
        conn = await self.s.connection()
        rows = await vec_knn(conn, "memory_vec", embedding, k=k * 2)
        if not rows:
            return []
        ids = [rid for rid, _ in rows]
        q = select(MemoryItem).where(MemoryItem.embed_id.in_(ids))
        if kind is not None:
            q = q.where(MemoryItem.kind == kind)
        r = await self.s.execute(q)
        by_eid = {it.embed_id: it for it in r.scalars().all()}
        out: list[tuple[MemoryItem, float]] = []
        for rid, dist in rows:
            it = by_eid.get(rid)
            if it is not None:
                out.append((it, dist))
        return out[:k]

    async def recent(
        self, kind: str, *, chat_id: int | None = None, limit: int = 20
    ) -> list[MemoryItem]:
        q = select(MemoryItem).where(MemoryItem.kind == kind)
        if chat_id is not None:
            q = q.where(MemoryItem.chat_id == chat_id)
        q = q.order_by(MemoryItem.ts.desc()).limit(limit)
        r = await self.s.execute(q)
        return list(r.scalars().all())

    async def forget_decayed(self, kind: str, max_decay: float = 1.0) -> int:
        r = await self.s.execute(
            delete(MemoryItem).where(
                and_(MemoryItem.kind == kind, MemoryItem.decay >= max_decay)
            )
        )
        return r.rowcount or 0
