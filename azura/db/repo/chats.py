"""Chats repository."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import Chat
from azura.utils.timez import ts


class ChatsRepo:
    """CRUD over the chats table."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def get(self, chat_id: int) -> Chat | None:
        return await self.s.get(Chat, chat_id)

    async def upsert(
        self,
        chat_id: int,
        kind: str,
        title: str | None = None,
        username: str | None = None,
    ) -> Chat:
        """Insert or refresh a chat row, updating last_seen."""
        now = ts()
        c = await self.get(chat_id)
        if c is None:
            c = Chat(
                id=chat_id,
                kind=kind,
                title=title,
                username=username,
                last_seen_ts=now,
                first_contact_ts=now,
            )
            self.s.add(c)
        else:
            c.kind = kind
            if title is not None:
                c.title = title
            if username is not None:
                c.username = username
            c.last_seen_ts = now
        await self.s.flush()
        return c

    async def set_muted(self, chat_id: int, muted: bool) -> None:
        await self.s.execute(update(Chat).where(Chat.id == chat_id).values(muted=muted))

    async def set_importance(self, chat_id: int, importance: int) -> None:
        await self.s.execute(
            update(Chat).where(Chat.id == chat_id).values(importance=importance)
        )

    async def adjust_opinion(self, chat_id: int, delta: int) -> int:
        c = await self.get(chat_id)
        if c is None:
            return 0
        c.opinion = max(-100, min(100, c.opinion + delta))
        await self.s.flush()
        return c.opinion

    async def list_by_kind(self, kind: str, muted: bool | None = None) -> list[Chat]:
        q = select(Chat).where(Chat.kind == kind)
        if muted is not None:
            q = q.where(Chat.muted.is_(muted))
        q = q.order_by(Chat.importance.desc(), Chat.last_seen_ts.desc())
        r = await self.s.execute(q)
        return list(r.scalars().all())

    async def all_active(self) -> list[Chat]:
        r = await self.s.execute(select(Chat).order_by(Chat.last_seen_ts.desc()))
        return list(r.scalars().all())
