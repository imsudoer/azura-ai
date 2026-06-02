"""Bootstrap of the entire database schema (ORM + FTS5 + sqlite-vec)."""
from __future__ import annotations

from azura.db.engine import get_engine
from azura.db.fts import create_fts
from azura.db.models import Base
from azura.db.vec import create_vec


async def init_schema(embed_dim: int) -> None:
    """Create ORM tables plus FTS5/vec virtual tables."""
    eng = get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_fts(conn)
        await create_vec(conn, embed_dim)
