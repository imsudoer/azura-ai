"""Attention log repository — records when the persona 'looks at' a chat."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import AttentionLog
from azura.utils.timez import ts


class AttentionRepo:
    """Persist attention-cycle audit entries."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def start(self, chat_id: int) -> AttentionLog:
        a = AttentionLog(chat_id=chat_id, started_ts=ts())
        self.s.add(a)
        await self.s.flush()
        return a

    async def finish(
        self,
        att_id: int,
        *,
        msgs_read: int = 0,
        decided: str | None = None,
        note: str | None = None,
    ) -> None:
        a = await self.s.get(AttentionLog, att_id)
        if a is None:
            return
        a.ended_ts = ts()
        a.msgs_read = msgs_read
        a.decided = decided
        a.note = note
        await self.s.flush()

    async def recent(self, limit: int = 50) -> list[AttentionLog]:
        r = await self.s.execute(
            select(AttentionLog).order_by(AttentionLog.started_ts.desc()).limit(limit)
        )
        return list(r.scalars().all())
