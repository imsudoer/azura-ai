"""GIF repository, mirror of stickers but without mood vectors."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import GifMedia
from azura.utils.timez import ts


class GifsRepo:
    """Persist GIFs the persona has seen or owns."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def get_by_file(self, file_id: str) -> GifMedia | None:
        r = await self.s.execute(select(GifMedia).where(GifMedia.file_id == file_id))
        return r.scalar_one_or_none()

    async def upsert(
        self,
        *,
        file_id: str,
        file_unique_id: str | None = None,
        tags: list[str] | None = None,
        description: str | None = None,
        local_path: str | None = None,
        fits_persona: float | None = None,
    ) -> GifMedia:
        g = await self.get_by_file(file_id)
        if g is None:
            g = GifMedia(
                file_id=file_id,
                file_unique_id=file_unique_id,
                tags=tags or [],
                description=description,
                local_path=local_path,
                fits_persona=fits_persona if fits_persona is not None else 0.5,
            )
            self.s.add(g)
        else:
            if tags:
                g.tags = list({*g.tags, *tags})
            if description is not None:
                g.description = description
            if local_path and not g.local_path:
                g.local_path = local_path
            if fits_persona is not None:
                g.fits_persona = fits_persona
        await self.s.flush()
        return g

    async def mark_used(self, gif_id: int) -> None:
        await self.s.execute(
            update(GifMedia)
            .where(GifMedia.id == gif_id)
            .values(usage_count=GifMedia.usage_count + 1, last_used_ts=ts())
        )

    async def pick_by_tags(self, tags: list[str], limit: int = 5) -> list[GifMedia]:
        r = await self.s.execute(select(GifMedia))
        items = list(r.scalars().all())
        wanted = {t.lower() for t in tags}
        def score(g: GifMedia) -> float:
            cur = {t.lower() for t in (g.tags or [])}
            overlap = len(wanted & cur)
            return overlap + g.fits_persona * 0.2
        items = [g for g in items if score(g) > 0]
        items.sort(key=score, reverse=True)
        return items[:limit]
