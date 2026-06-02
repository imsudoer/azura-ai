"""Relationships service: who-knows-whom edges between peers."""
from __future__ import annotations

from azura.db.repo import Repos


class Relationships:
    """Observed bonds inside group chats."""

    def __init__(self, repos: Repos) -> None:
        self.r = repos

    async def note(
        self,
        a: int,
        b: int,
        *,
        kind: str,
        chat_id: int | None = None,
        strength: float = 0.5,
        notes: str | None = None,
    ) -> None:
        await self.r.relationships.upsert(
            a, b, kind=kind, chat_id=chat_id, strength=strength, notes=notes
        )

    async def around(self, user_id: int, limit: int = 20) -> list[dict]:
        rels = await self.r.relationships.around(user_id, limit=limit)
        out: list[dict] = []
        for r in rels:
            other = r.b_id if r.a_id == user_id else r.a_id
            out.append({"other": other, "kind": r.kind, "strength": r.strength})
        return out
