"""Inner journal repository — first-person introspection log."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import JournalEntry
from azura.utils.timez import ts


class JournalRepo:
    """Persist journal entries to DB and optionally mirror them into monthly md files."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def write(
        self,
        text: str,
        *,
        kind: str = "thought",
        chat_id: int | None = None,
        user_id: int | None = None,
        meta: dict | None = None,
        mirror_dir: Path | None = None,
    ) -> JournalEntry:
        now = ts()
        e = JournalEntry(
            ts=now,
            kind=kind,
            text=text,
            chat_id=chat_id,
            user_id=user_id,
            meta=meta or {},
        )
        self.s.add(e)
        await self.s.flush()
        if mirror_dir is not None:
            self._mirror(text, kind, now, mirror_dir)
        return e

    @staticmethod
    def _mirror(text: str, kind: str, ts_: int, mirror_dir: Path) -> None:
        """Append the entry to YYYY-MM.md and _current.md."""
        mirror_dir.mkdir(parents=True, exist_ok=True)
        dt = datetime.fromtimestamp(ts_, timezone.utc)
        monthly = mirror_dir / f"{dt:%Y-%m}.md"
        current = mirror_dir / "_current.md"
        line = f"- **{dt:%Y-%m-%d %H:%M}** _[{kind}]_ {text}\n"
        with monthly.open("a", encoding="utf-8") as f:
            f.write(line)
        with current.open("a", encoding="utf-8") as f:
            f.write(line)

    async def recent(self, limit: int = 50, kind: str | None = None) -> list[JournalEntry]:
        q = select(JournalEntry).order_by(JournalEntry.ts.desc()).limit(limit)
        if kind is not None:
            q = q.where(JournalEntry.kind == kind)
        r = await self.s.execute(q)
        return list(r.scalars().all())
