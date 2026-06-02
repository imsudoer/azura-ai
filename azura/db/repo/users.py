"""Users repository."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import User
from azura.utils.timez import ts


class UsersRepo:
    """CRUD over the users table."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def get(self, user_id: int) -> User | None:
        return await self.s.get(User, user_id)

    async def upsert(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        is_bot: bool = False,
    ) -> User:
        """Insert or refresh a user; bumps last_seen and interactions."""
        now = ts()
        u = await self.get(user_id)
        if u is None:
            u = User(
                id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_bot=is_bot,
                first_contact_ts=now,
                last_seen_ts=now,
            )
            self.s.add(u)
        else:
            if username is not None:
                u.username = username
            if first_name is not None:
                u.first_name = first_name
            if last_name is not None:
                u.last_name = last_name
            u.is_bot = is_bot
            u.last_seen_ts = now
        await self.s.flush()
        return u

    async def touch(self, user_id: int) -> None:
        await self.s.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_seen_ts=ts(), interactions=User.interactions + 1)
        )

    async def adjust_opinion(self, user_id: int, delta: int) -> int:
        u = await self.get(user_id)
        if u is None:
            return 0
        u.opinion = max(-100, min(100, u.opinion + delta))
        await self.s.flush()
        return u.opinion

    async def set_notes(self, user_id: int, notes: str) -> None:
        await self.s.execute(update(User).where(User.id == user_id).values(notes=notes))

    async def by_username(self, username: str) -> User | None:
        r = await self.s.execute(select(User).where(User.username == username))
        return r.scalar_one_or_none()
