"""Messages repository (hot ring buffer; full archive lives in chat_archive)."""
from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.fts import fts_insert_message
from azura.db.models import Message


class MessagesRepo:
    """Persist hot messages, mark seen, trim while preserving reply-chains."""

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
        media_group_id: str | None = None,
        forward_from_id: int | None = None,
        forward_from_chat_id: int | None = None,
        reactions: list | None = None,
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
            media_group_id=media_group_id,
            forward_from_id=forward_from_id,
            forward_from_chat_id=forward_from_chat_id,
            reactions=reactions or [],
            meta=meta or {},
        )
        self.s.add(m)
        await self.s.flush()
        if text:
            conn = await self.s.connection()
            await fts_insert_message(conn, m.id, chat_id, text)
        return m

    async def mark_edited(self, chat_id: int, tg_msg_id: int, new_text: str | None, edited_ts: int) -> Message | None:
        r = await self.s.execute(
            select(Message).where(
                Message.chat_id == chat_id, Message.tg_msg_id == tg_msg_id
            )
        )
        m = r.scalar_one_or_none()
        if m is None:
            return None
        m.text = new_text if new_text is not None else m.text
        m.edited_ts = edited_ts
        await self.s.flush()
        return m

    async def mark_deleted(self, chat_id: int, tg_msg_id: int, deleted_ts: int) -> Message | None:
        r = await self.s.execute(
            select(Message).where(
                Message.chat_id == chat_id, Message.tg_msg_id == tg_msg_id
            )
        )
        m = r.scalar_one_or_none()
        if m is None:
            return None
        m.deleted_ts = deleted_ts
        await self.s.flush()
        return m

    async def update_reactions(self, chat_id: int, tg_msg_id: int, reactions: list) -> Message | None:
        r = await self.s.execute(
            select(Message).where(
                Message.chat_id == chat_id, Message.tg_msg_id == tg_msg_id
            )
        )
        m = r.scalar_one_or_none()
        if m is None:
            return None
        m.reactions = reactions
        await self.s.flush()
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

    async def get_by_tg_id(self, chat_id: int, tg_msg_id: int) -> Message | None:
        r = await self.s.execute(
            select(Message).where(
                Message.chat_id == chat_id, Message.tg_msg_id == tg_msg_id
            )
        )
        return r.scalar_one_or_none()

    async def album(self, chat_id: int, media_group_id: str) -> list[Message]:
        """All messages of an album, ordered by ts."""
        r = await self.s.execute(
            select(Message)
            .where(Message.chat_id == chat_id, Message.media_group_id == media_group_id)
            .order_by(Message.ts.asc())
        )
        return list(r.scalars().all())

    async def trim(self, chat_id: int, keep: int = 2000) -> int:
        """Trim a chat down to its last `keep` messages.

        Reply-chain protection: never drop a message that is referenced by a
        kept message's `reply_to`. The archive table preserves history regardless.
        """
        r = await self.s.execute(
            select(Message.id, Message.tg_msg_id)
            .where(Message.chat_id == chat_id)
            .order_by(Message.ts.desc())
            .limit(keep)
        )
        kept = list(r.fetchall())
        if not kept:
            return 0
        kept_ids = {row[0] for row in kept}
        r2 = await self.s.execute(
            select(Message.reply_to).where(
                Message.chat_id == chat_id, Message.id.in_(kept_ids),
                Message.reply_to.is_not(None),
            )
        )
        protect = {row[0] for row in r2.fetchall() if row[0] is not None}
        r3 = await self.s.execute(
            select(Message.id, Message.tg_msg_id)
            .where(Message.chat_id == chat_id, Message.id.notin_(kept_ids))
        )
        candidates = [row for row in r3.fetchall() if row[1] not in protect]
        if not candidates:
            return 0
        await self.s.execute(delete(Message).where(Message.id.in_([c[0] for c in candidates])))
        return len(candidates)
