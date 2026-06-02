"""Generic key/value scratch store."""
from __future__ import annotations

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.models import KV
from azura.utils.timez import ts


class KVRepo:
    """Persist transient scalar/JSON state by string key."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def get(self, key: str) -> str | None:
        r = await self.s.execute(select(KV).where(KV.key == key))
        row = r.scalar_one_or_none()
        return row.value if row else None

    async def get_json(self, key: str):
        v = await self.get(key)
        if v is None:
            return None
        return orjson.loads(v)

    async def set(self, key: str, value: str) -> None:
        row = await self.s.get(KV, key)
        if row is None:
            self.s.add(KV(key=key, value=value, updated_ts=ts()))
        else:
            row.value = value
            row.updated_ts = ts()
        await self.s.flush()

    async def set_json(self, key: str, value) -> None:
        await self.set(key, orjson.dumps(value).decode())

    async def delete(self, key: str) -> None:
        row = await self.s.get(KV, key)
        if row is not None:
            await self.s.delete(row)
            await self.s.flush()
