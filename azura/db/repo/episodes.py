"""Episodic memory repository: 'I remember that one time...'."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.fts import fts_insert_episode, fts_search_episodes
from azura.db.models import Episode
from azura.db.vec import vec_insert, vec_knn
from azura.utils.timez import ts


class EpisodesRepo:
    """CRUD over Episode with FTS + vec indices."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def add(
        self,
        *,
        title: str,
        summary: str,
        chat_id: int | None = None,
        user_id: int | None = None,
        emotion: str | None = None,
        intensity: float = 0.5,
        when_ts: int | None = None,
        embedding: list[float] | None = None,
        meta: dict | None = None,
    ) -> Episode:
        e = Episode(
            chat_id=chat_id,
            user_id=user_id,
            when_ts=when_ts or ts(),
            title=title,
            summary=summary,
            emotion=emotion,
            intensity=intensity,
            meta=meta or {},
        )
        self.s.add(e)
        await self.s.flush()
        conn = await self.s.connection()
        await fts_insert_episode(conn, e.id, title, summary)
        if embedding is not None:
            e.embed_id = await vec_insert(conn, "episodes_vec", embedding)
            await self.s.flush()
        return e

    async def recent(
        self, *, chat_id: int | None = None, user_id: int | None = None, limit: int = 20
    ) -> list[Episode]:
        q = select(Episode)
        if chat_id is not None:
            q = q.where(Episode.chat_id == chat_id)
        if user_id is not None:
            q = q.where(Episode.user_id == user_id)
        q = q.order_by(Episode.when_ts.desc()).limit(limit)
        r = await self.s.execute(q)
        return list(r.scalars().all())

    async def search_text(self, query: str, limit: int = 10) -> list[Episode]:
        conn = await self.s.connection()
        ids = await fts_search_episodes(conn, query, limit=limit * 2)
        if not ids:
            return []
        r = await self.s.execute(select(Episode).where(Episode.id.in_(ids)))
        items = {it.id: it for it in r.scalars().all()}
        return [items[i] for i in ids if i in items][:limit]

    async def search_vec(
        self, embedding: list[float], k: int = 8
    ) -> list[tuple[Episode, float]]:
        conn = await self.s.connection()
        rows = await vec_knn(conn, "episodes_vec", embedding, k=k * 2)
        if not rows:
            return []
        ids = [rid for rid, _ in rows]
        r = await self.s.execute(select(Episode).where(Episode.embed_id.in_(ids)))
        by_eid = {it.embed_id: it for it in r.scalars().all()}
        out: list[tuple[Episode, float]] = []
        for rid, dist in rows:
            it = by_eid.get(rid)
            if it is not None:
                out.append((it, dist))
        return out[:k]
