"""FTS5 virtual tables and helpers for full-text recall."""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_TOK_RE = re.compile(r"\w+", re.UNICODE)


def fts_quote(query: str) -> str:
    """Safely escape a user query for FTS5 MATCH: keep word tokens, quote them."""
    toks = _TOK_RE.findall(query or "")
    if not toks:
        return '""'
    return " ".join(f'"{t}"' for t in toks)

FTS_TABLES_DDL = (
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
        content,
        topic,
        memory_id UNINDEXED,
        tokenize='unicode61 remove_diacritics 2'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
        title,
        summary,
        episode_id UNINDEXED,
        tokenize='unicode61 remove_diacritics 2'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        text,
        message_id UNINDEXED,
        chat_id UNINDEXED,
        tokenize='unicode61 remove_diacritics 2'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS archive_fts USING fts5(
        text,
        caption,
        description,
        archive_id UNINDEXED,
        chat_id UNINDEXED,
        tokenize='unicode61 remove_diacritics 2'
    )
    """,
)


async def create_fts(conn: AsyncConnection) -> None:
    """Create FTS5 virtual tables if missing."""
    for ddl in FTS_TABLES_DDL:
        await conn.execute(text(ddl))


async def fts_insert_memory(conn: AsyncConnection, memory_id: int, content: str, topic: str | None) -> None:
    await conn.execute(
        text("INSERT INTO memory_fts(memory_id, content, topic) VALUES (:i, :c, :t)"),
        {"i": memory_id, "c": content or "", "t": topic or ""},
    )


async def fts_insert_episode(conn: AsyncConnection, episode_id: int, title: str, summary: str) -> None:
    await conn.execute(
        text("INSERT INTO episodes_fts(episode_id, title, summary) VALUES (:i, :t, :s)"),
        {"i": episode_id, "t": title or "", "s": summary or ""},
    )


async def fts_insert_message(conn: AsyncConnection, message_id: int, chat_id: int, txt: str) -> None:
    await conn.execute(
        text("INSERT INTO messages_fts(message_id, chat_id, text) VALUES (:i, :c, :t)"),
        {"i": message_id, "c": chat_id, "t": txt or ""},
    )


async def fts_search_memory(conn: AsyncConnection, query: str, limit: int = 10) -> list[int]:
    """Return memory ids matching a query, ranked by bm25."""
    q = fts_quote(query)
    if q == '""':
        return []
    r = await conn.execute(
        text(
            "SELECT memory_id FROM memory_fts WHERE memory_fts MATCH :q "
            "ORDER BY bm25(memory_fts) LIMIT :l"
        ),
        {"q": q, "l": limit},
    )
    return [row[0] for row in r.fetchall()]


async def fts_insert_archive(
    conn: AsyncConnection,
    archive_id: int,
    chat_id: int,
    text_: str,
    caption: str,
    description: str,
) -> None:
    """Index an archive row by its text / caption / vision-description."""
    await conn.execute(
        text(
            "INSERT INTO archive_fts(archive_id, chat_id, text, caption, description) "
            "VALUES (:i, :c, :t, :cap, :d)"
        ),
        {"i": archive_id, "c": chat_id, "t": text_ or "", "cap": caption or "", "d": description or ""},
    )


async def fts_search_archive(
    conn: AsyncConnection, query: str, *, chat_id: int | None = None, limit: int = 20
) -> list[int]:
    """Return archive ids matching a query, optionally scoped to one chat."""
    q = fts_quote(query)
    if q == '""':
        return []
    sql = (
        "SELECT archive_id FROM archive_fts WHERE archive_fts MATCH :q"
        + (" AND chat_id = :ch" if chat_id is not None else "")
        + " ORDER BY bm25(archive_fts) LIMIT :l"
    )
    params: dict = {"q": q, "l": limit}
    if chat_id is not None:
        params["ch"] = chat_id
    r = await conn.execute(text(sql), params)
    return [row[0] for row in r.fetchall()]


async def fts_search_episodes(conn: AsyncConnection, query: str, limit: int = 10) -> list[int]:
    q = fts_quote(query)
    if q == '""':
        return []
    r = await conn.execute(
        text(
            "SELECT episode_id FROM episodes_fts WHERE episodes_fts MATCH :q "
            "ORDER BY bm25(episodes_fts) LIMIT :l"
        ),
        {"q": q, "l": limit},
    )
    return [row[0] for row in r.fetchall()]
