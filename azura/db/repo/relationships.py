"""Relationships repository: observed bonds between peers (social graph)."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import Relationship
from azura.utils.timez import ts


class RelationshipsRepo:
    """Persist edges of the observed social graph."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    @staticmethod
    def _norm(a: int, b: int) -> tuple[int, int]:
        return (a, b) if a <= b else (b, a)

    async def get(self, a: int, b: int, chat_id: int | None = None) -> Relationship | None:
        a, b = self._norm(a, b)
        r = await self.s.execute(
            select(Relationship).where(
                Relationship.a_id == a,
                Relationship.b_id == b,
                Relationship.chat_id.is_(chat_id) if chat_id is None else Relationship.chat_id == chat_id,
            )
        )
        return r.scalar_one_or_none()

    async def upsert(
        self,
        a: int,
        b: int,
        *,
        kind: str = "neutral",
        chat_id: int | None = None,
        strength: float = 0.5,
        notes: str | None = None,
    ) -> Relationship:
        a, b = self._norm(a, b)
        rel = await self.get(a, b, chat_id)
        now = ts()
        if rel is None:
            rel = Relationship(
                a_id=a,
                b_id=b,
                chat_id=chat_id,
                kind=kind,
                strength=max(0.0, min(1.0, strength)),
                notes=notes,
                updated_ts=now,
            )
            self.s.add(rel)
        else:
            rel.kind = kind
            rel.strength = max(0.0, min(1.0, strength))
            if notes:
                rel.notes = notes
            rel.updated_ts = now
        await self.s.flush()
        return rel

    async def around(self, user_id: int, limit: int = 50) -> list[Relationship]:
        r = await self.s.execute(
            select(Relationship)
            .where(or_(Relationship.a_id == user_id, Relationship.b_id == user_id))
            .order_by(Relationship.strength.desc())
            .limit(limit)
        )
        return list(r.scalars().all())
