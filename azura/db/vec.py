"""sqlite-vec virtual tables and similarity search helpers."""
from __future__ import annotations

import struct

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


def _pack(vec: list[float]) -> bytes:
    """Pack a float32 vector into the binary format sqlite-vec expects."""
    return struct.pack(f"{len(vec)}f", *vec)


def vec_tables_ddl(dim: int) -> tuple[str, ...]:
    """Return DDL for vec0 virtual tables parameterised by embedding dim."""
    return (
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0(
            embedding float[{dim}]
        )
        """,
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS episodes_vec USING vec0(
            embedding float[{dim}]
        )
        """,
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS stickers_vec USING vec0(
            embedding float[{dim}]
        )
        """,
    )


async def create_vec(conn: AsyncConnection, dim: int) -> None:
    """Create vec0 virtual tables if missing."""
    for ddl in vec_tables_ddl(dim):
        await conn.execute(text(ddl))


async def vec_insert(conn: AsyncConnection, table: str, vector: list[float]) -> int:
    """Insert an embedding and return the rowid."""
    r = await conn.execute(
        text(f"INSERT INTO {table}(embedding) VALUES (:e)"),
        {"e": _pack(vector)},
    )
    rid = r.lastrowid
    if rid is None:
        rid_row = await conn.execute(text("SELECT last_insert_rowid()"))
        rid = rid_row.scalar_one()
    return int(rid)


async def vec_update(conn: AsyncConnection, table: str, rowid: int, vector: list[float]) -> None:
    """Replace the embedding for a given rowid."""
    await conn.execute(
        text(f"UPDATE {table} SET embedding=:e WHERE rowid=:r"),
        {"e": _pack(vector), "r": rowid},
    )


async def vec_delete(conn: AsyncConnection, table: str, rowid: int) -> None:
    await conn.execute(text(f"DELETE FROM {table} WHERE rowid=:r"), {"r": rowid})


async def vec_knn(
    conn: AsyncConnection, table: str, vector: list[float], k: int = 8
) -> list[tuple[int, float]]:
    """k-NN search, returning [(rowid, distance), ...] sorted ascending."""
    r = await conn.execute(
        text(
            f"SELECT rowid, distance FROM {table} "
            f"WHERE embedding MATCH :e ORDER BY distance LIMIT :k"
        ),
        {"e": _pack(vector), "k": k},
    )
    return [(int(row[0]), float(row[1])) for row in r.fetchall()]
