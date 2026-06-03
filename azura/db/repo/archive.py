"""ChatArchive repository: never-trimmed full chat history with FTS5 search."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.fts import fts_insert_archive, fts_search_archive
from azura.db.models import ChatArchive


class ArchiveRepo:
    """Persist every observed message forever, with rich metadata and FTS."""

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
        caption: str | None = None,
        reply_to: int | None = None,
        is_self: bool = False,
        media_group_id: str | None = None,
        forward_from_id: int | None = None,
        forward_from_chat_id: int | None = None,
        media: dict | None = None,
        local_path: str | None = None,
        description: str | None = None,
        service_kind: str | None = None,
        reactions: list | None = None,
        meta: dict | None = None,
    ) -> ChatArchive:
        """Insert an archive row; idempotent on (chat_id, tg_msg_id)."""
        existing = await self.s.execute(
            select(ChatArchive).where(
                ChatArchive.chat_id == chat_id, ChatArchive.tg_msg_id == tg_msg_id
            )
        )
        a = existing.scalar_one_or_none()
        if a is not None:
            return a
        a = ChatArchive(
            chat_id=chat_id, tg_msg_id=tg_msg_id, from_id=from_id, ts=ts_,
            kind=kind, text=text, caption=caption, reply_to=reply_to, is_self=is_self,
            media_group_id=media_group_id, forward_from_id=forward_from_id,
            forward_from_chat_id=forward_from_chat_id,
            media=media or {}, local_path=local_path, description=description,
            service_kind=service_kind, reactions=reactions or [], meta=meta or {},
        )
        self.s.add(a)
        await self.s.flush()
        if text or caption or description:
            conn = await self.s.connection()
            await fts_insert_archive(conn, a.id, chat_id, text or "", caption or "", description or "")
        return a

    async def get_by_tg_id(self, chat_id: int, tg_msg_id: int) -> ChatArchive | None:
        r = await self.s.execute(
            select(ChatArchive).where(
                ChatArchive.chat_id == chat_id, ChatArchive.tg_msg_id == tg_msg_id
            )
        )
        return r.scalar_one_or_none()

    async def by_ids(self, ids: list[int]) -> list[ChatArchive]:
        if not ids:
            return []
        r = await self.s.execute(select(ChatArchive).where(ChatArchive.id.in_(ids)))
        rows = r.scalars().all()
        order = {x: i for i, x in enumerate(ids)}
        return sorted(rows, key=lambda a: order.get(a.id, 1_000_000))

    async def reply_chain(
        self, chat_id: int, tg_msg_id: int, *, max_depth: int = 5
    ) -> list[ChatArchive]:
        """Walk reply-to ancestors up to max_depth. Oldest-first."""
        chain: list[ChatArchive] = []
        seen: set[int] = set()
        cur_id = tg_msg_id
        for _ in range(max_depth):
            if cur_id in seen:
                break
            seen.add(cur_id)
            row = await self.get_by_tg_id(chat_id, cur_id)
            if row is None:
                break
            chain.append(row)
            if row.reply_to is None:
                break
            cur_id = row.reply_to
        return list(reversed(chain))

    async def album(self, chat_id: int, media_group_id: str) -> list[ChatArchive]:
        r = await self.s.execute(
            select(ChatArchive)
            .where(ChatArchive.chat_id == chat_id, ChatArchive.media_group_id == media_group_id)
            .order_by(ChatArchive.ts.asc())
        )
        return list(r.scalars().all())

    async def update_reactions(self, chat_id: int, tg_msg_id: int, reactions: list) -> ChatArchive | None:
        a = await self.get_by_tg_id(chat_id, tg_msg_id)
        if a is None:
            return None
        a.reactions = reactions
        await self.s.flush()
        return a

    async def mark_edited(self, chat_id: int, tg_msg_id: int, new_text: str | None, edited_ts: int) -> ChatArchive | None:
        a = await self.get_by_tg_id(chat_id, tg_msg_id)
        if a is None:
            return None
        if new_text is not None:
            history = list(a.meta.get("edits", []))
            history.append({"ts": a.edited_ts or a.ts, "text": a.text})
            new_meta = dict(a.meta)
            new_meta["edits"] = history
            a.meta = new_meta
            a.text = new_text
        a.edited_ts = edited_ts
        await self.s.flush()
        return a

    async def mark_deleted(self, chat_id: int, tg_msg_id: int, deleted_ts: int) -> ChatArchive | None:
        a = await self.get_by_tg_id(chat_id, tg_msg_id)
        if a is None:
            return None
        a.deleted_ts = deleted_ts
        await self.s.flush()
        return a

    async def attach_local_path(self, archive_id: int, local_path: str) -> None:
        a = await self.s.get(ChatArchive, archive_id)
        if a is None:
            return
        a.local_path = local_path
        await self.s.flush()

    async def attach_description(self, archive_id: int, description: str) -> None:
        """Save vision description and re-index FTS."""
        a = await self.s.get(ChatArchive, archive_id)
        if a is None:
            return
        a.description = description
        await self.s.flush()
        conn = await self.s.connection()
        await fts_insert_archive(
            conn, a.id, a.chat_id, a.text or "", a.caption or "", description
        )

    async def search(
        self, query: str, *, chat_id: int | None = None, limit: int = 20
    ) -> list[ChatArchive]:
        conn = await self.s.connection()
        ids = await fts_search_archive(conn, query, chat_id=chat_id, limit=limit)
        if not ids:
            return []
        return await self.by_ids(ids)

    async def recent(
        self, chat_id: int, *, limit: int = 50, include_deleted: bool = False
    ) -> list[ChatArchive]:
        q = select(ChatArchive).where(ChatArchive.chat_id == chat_id)
        if not include_deleted:
            q = q.where(ChatArchive.deleted_ts.is_(None))
        q = q.order_by(ChatArchive.ts.desc()).limit(limit)
        r = await self.s.execute(q)
        return list(reversed(r.scalars().all()))

    async def last_self_ts(self) -> int | None:
        """Timestamp of the most recent message authored by the persona, across all chats."""
        from sqlalchemy import func
        q = select(func.max(ChatArchive.ts)).where(ChatArchive.is_self.is_(True))
        r = await self.s.execute(q)
        return r.scalar()
