"""Episodic memory wrapper: remembered events with emotion + intensity."""
from __future__ import annotations

from azura.db.repo import Repos


class Episodic:
    """High-level API over EpisodesRepo."""

    def __init__(self, repos: Repos) -> None:
        self.r = repos

    async def remember(
        self,
        *,
        title: str,
        summary: str,
        chat_id: int | None = None,
        user_id: int | None = None,
        emotion: str | None = None,
        intensity: float = 0.5,
        embedding: list[float] | None = None,
    ) -> int:
        e = await self.r.episodes.add(
            title=title,
            summary=summary,
            chat_id=chat_id,
            user_id=user_id,
            emotion=emotion,
            intensity=intensity,
            embedding=embedding,
        )
        return e.id

    async def with_user(self, user_id: int, limit: int = 10) -> list[str]:
        items = await self.r.episodes.recent(user_id=user_id, limit=limit)
        return [f"{e.title}: {e.summary}" for e in items]

    async def search(self, query: str, *, limit: int = 8) -> list[str]:
        items = await self.r.episodes.search_text(query, limit=limit)
        return [f"{e.title}: {e.summary}" for e in items]

    async def search_vec(self, embedding: list[float], *, k: int = 8) -> list[str]:
        items = await self.r.episodes.search_vec(embedding, k=k)
        return [f"{e.title}: {e.summary}" for e, _ in items]
