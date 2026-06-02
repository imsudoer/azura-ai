"""Messages repository (raw seen messages + per-chat ring buffer)."""
from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.fts import fts_insert_message
from azura.db.models import Message


class MessagesRepo:
    """Persist seen messages and trim per-chat history to a rolling window."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def add(
        self,
        *,
        chat_id: int,
        tg_msg_id: int,
        from_id: int | None,
        ts_: int,
        kind: str = "text",
        text: str | None = None,
        reply_to: int | None = None,
        media_ref: str | None = None,
        is_self: bool = False,
        meta: dict | None = None,
    ) -> Message:
        """Insert a message row; idempotent on (chat_id, tg_msg_id)."""
        existing = await self.s.execute(
            select(Message).where(
                Message.chat_id == chat_id, Message.tg_msg_id == tg_msg_id
            )
        )
        m = existing.scalar_one_or_none()
        if m is not None:
            return m
        m = Message(
            chat_id=chat_id,
            tg_msg_id=tg_msg_id,
            from_id=from_id,
            ts=ts_,
            kind=kind,
            text=text,
            reply_to=reply_to,
            media_ref=media_ref,
            is_self=is_self,
            meta=meta or {},
        )
        self.s.add(m)
        await self.s.flush()
        if text:
            conn = await self.s.connection()
            await fts_insert_message(conn, m.id, chat_id, text)
        return m

    async def mark_seen(self, chat_id: int, up_to_tg_msg_id: int) -> int:
        """Mark unseen messages up to a given tg msg id as seen."""
        r = await self.s.execute(
            update(Message)
            .where(
                Message.chat_id == chat_id,
                Message.tg_msg_id <= up_to_tg_msg_id,
                Message.seen.is_(False),
            )
            .values(seen=True)
        )
        return r.rowcount or 0

    async def unseen_count(self, chat_id: int) -> int:
        r = await self.s.execute(
            select(Message)
            .where(Message.chat_id == chat_id, Message.seen.is_(False))
        )
        return len(list(r.scalars()))

    async def last_n(self, chat_id: int, n: int = 50) -> list[Message]:
        r = await self.s.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.ts.desc())
            .limit(n)
        )
        return list(reversed(r.scalars().all()))

    async def trim(self, chat_id: int, keep: int = 500) -> int:
        """Trim a chat down to its last `keep` messages."""
        r = await self.s.execute(
            select(Message.id)
            .where(Message.chat_id == chat_id)
            .order_by(Message.ts.desc())
            .offset(keep)
        )
        ids = [row[0] for row in r.fetchall()]
        if not ids:
            return 0
        await self.s.execute(delete(Message).where(Message.id.in_(ids)))
        return len(ids)
