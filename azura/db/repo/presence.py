"""Presence log repository."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import PresenceLog
from azura.utils.timez import ts


class PresenceRepo:
    """Persist presence transitions over time."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def push(self, state: str, *, reason: str | None = None, until_ts: int | None = None) -> PresenceLog:
        p = PresenceLog(state=state, reason=reason, until_ts=until_ts, started_ts=ts())
        self.s.add(p)
        await self.s.flush()
        return p

    async def current(self) -> PresenceLog | None:
        r = await self.s.execute(
            select(PresenceLog).order_by(PresenceLog.started_ts.desc()).limit(1)
        )
        return r.scalar_one_or_none()

    async def recent(self, limit: int = 20) -> list[PresenceLog]:
        r = await self.s.execute(
            select(PresenceLog).order_by(PresenceLog.started_ts.desc()).limit(limit)
        )
        return list(r.scalars().all())
