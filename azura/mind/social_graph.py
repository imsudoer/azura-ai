"""Social-graph helpers built on top of Relationships repo."""
from __future__ import annotations

from azura.memory.service import MemoryService


class SocialGraph:
    """Pretty wrapper around peer-to-peer edges."""

    def __init__(self, memory: MemoryService) -> None:
        self.m = memory

    async def neighbors(self, user_id: int, *, min_strength: float = 0.3) -> list[dict]:
        rels = await self.m.relationships.around(user_id)
        return [r for r in rels if r["strength"] >= min_strength]

    async def picks_side(self, persona_loyalty: float, a_id: int, b_id: int) -> int | None:
        """If the persona has strong bond with one side, return their id; else None."""
        if persona_loyalty < 0.55:
            return None
        op_a = await self.m.opinions.user(a_id)
        op_b = await self.m.opinions.user(b_id)
        if abs(op_a - op_b) < 15:
            return None
        return a_id if op_a > op_b else b_id
