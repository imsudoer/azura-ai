"""Opinions repository (user/chat/topic targets)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import Opinion
from azura.utils.timez import ts


class OpinionsRepo:
    """Persist and update opinions of the persona about targets."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def get(self, target_kind: str, target_id: int) -> Opinion | None:
        r = await self.s.execute(
            select(Opinion).where(
                Opinion.target_kind == target_kind, Opinion.target_id == target_id
            )
        )
        return r.scalar_one_or_none()

    async def upsert(
        self,
        target_kind: str,
        target_id: int,
        *,
        delta: int = 0,
        tags: list[str] | None = None,
        reason: str | None = None,
    ) -> Opinion:
        """Adjust an existing opinion or create a new one."""
        op = await self.get(target_kind, target_id)
        now = ts()
        if op is None:
            op = Opinion(
                target_kind=target_kind,
                target_id=target_id,
                score=max(-100, min(100, delta)),
                tags=tags or [],
                reason=reason,
                updated_ts=now,
            )
            self.s.add(op)
        else:
            op.score = max(-100, min(100, op.score + delta))
            if tags:
                merged = list({*op.tags, *tags})
                op.tags = merged
            if reason:
                op.reason = reason
            op.updated_ts = now
        await self.s.flush()
        return op

    async def list_for_chat(self, chat_user_ids: list[int]) -> list[Opinion]:
        if not chat_user_ids:
            return []
        r = await self.s.execute(
            select(Opinion).where(
                Opinion.target_kind == "user", Opinion.target_id.in_(chat_user_ids)
            )
        )
        return list(r.scalars().all())

    async def top_n(self, target_kind: str, n: int = 20, positive: bool = True) -> list[Opinion]:
        q = select(Opinion).where(Opinion.target_kind == target_kind)
        q = q.order_by(Opinion.score.desc() if positive else Opinion.score.asc()).limit(n)
        r = await self.s.execute(q)
        return list(r.scalars().all())
