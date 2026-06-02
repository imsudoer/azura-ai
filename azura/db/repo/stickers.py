"""Stickers repository: collected + tagged stickers, with persona-fit scoring."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import Sticker
from azura.db.vec import vec_insert, vec_knn
from azura.utils.timez import ts


class StickersRepo:
    """Persist and search stickers by tag, mood and embedding similarity."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def get_by_file(self, file_id: str) -> Sticker | None:
        r = await self.s.execute(select(Sticker).where(Sticker.file_id == file_id))
        return r.scalar_one_or_none()

    async def upsert(
        self,
        *,
        file_id: str,
        file_unique_id: str | None = None,
        set_name: str | None = None,
        emoji: str | None = None,
        local_path: str | None = None,
    ) -> Sticker:
        st = await self.get_by_file(file_id)
        if st is None:
            st = Sticker(
                file_id=file_id,
                file_unique_id=file_unique_id,
                set_name=set_name,
                emoji=emoji,
                local_path=local_path,
            )
            self.s.add(st)
        else:
            if set_name and not st.set_name:
                st.set_name = set_name
            if emoji and not st.emoji:
                st.emoji = emoji
            if local_path and not st.local_path:
                st.local_path = local_path
        await self.s.flush()
        return st

    async def tag(
        self,
        sticker_id: int,
        *,
        tags: list[str] | None = None,
        mood_valence: float | None = None,
        mood_arousal: float | None = None,
        description: str | None = None,
        fits_persona: float | None = None,
        embedding: list[float] | None = None,
    ) -> Sticker:
        st = await self.s.get(Sticker, sticker_id)
        if st is None:
            raise KeyError(sticker_id)
        if tags is not None:
            st.tags = list({*st.tags, *tags})
        if mood_valence is not None:
            st.mood_valence = max(-1.0, min(1.0, mood_valence))
        if mood_arousal is not None:
            st.mood_arousal = max(0.0, min(1.0, mood_arousal))
        if description is not None:
            st.description = description
        if fits_persona is not None:
            st.fits_persona = max(0.0, min(1.0, fits_persona))
        if embedding is not None:
            conn = await self.s.connection()
            await vec_insert(conn, "stickers_vec", embedding)
        await self.s.flush()
        return st

    async def mark_used(self, sticker_id: int) -> None:
        await self.s.execute(
            update(Sticker)
            .where(Sticker.id == sticker_id)
            .values(usage_count=Sticker.usage_count + 1, last_used_ts=ts())
        )

    async def pick_by_mood(
        self,
        *,
        valence: float,
        arousal: float,
        min_fit: float = 0.5,
        limit: int = 5,
    ) -> list[Sticker]:
        """Pick stickers whose mood roughly matches and which fit the persona."""
        r = await self.s.execute(
            select(Sticker).where(Sticker.fits_persona >= min_fit)
        )
        items = list(r.scalars().all())
        def score(st: Sticker) -> float:
            dv = abs(st.mood_valence - valence)
            da = abs(st.mood_arousal - arousal)
            return -(dv + da) + st.fits_persona * 0.2
        items.sort(key=score, reverse=True)
        return items[:limit]

    async def search_vec(self, embedding: list[float], k: int = 5) -> list[int]:
        conn = await self.s.connection()
        rows = await vec_knn(conn, "stickers_vec", embedding, k=k)
        return [rid for rid, _ in rows]
