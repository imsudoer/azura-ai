"""SQLAlchemy async engine wired to sqlite (WAL) + sqlite-vec extension."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_maker: async_sessionmaker[AsyncSession] | None = None

_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=268435456",
    "PRAGMA cache_size=-65536",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
)


def _unwrap(conn):
    """Return the underlying stdlib sqlite3.Connection from any aiosqlite/proxy wrapper."""
    seen = set()
    cur = conn
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, sqlite3.Connection):
            return cur
        seen.add(id(cur))
        cur = getattr(cur, "_connection", None) or getattr(cur, "connection", None) or getattr(cur, "_conn", None)
    return conn


def _on_connect(dbapi_conn, _record):
    """Connection-time hook: enable extension load, attach sqlite-vec, apply pragmas."""
    raw = _unwrap(dbapi_conn)
    try:
        raw.enable_load_extension(True)
        sqlite_vec.load(raw)
    finally:
        try:
            raw.enable_load_extension(False)
        except Exception:
            pass
    cur = raw.cursor()
    for p in _PRAGMAS:
        cur.execute(p)
    cur.close()


def init_engine(db_path: Path) -> AsyncEngine:
    """Create the async engine (idempotent)."""
    global _engine, _maker
    if _engine is not None:
        return _engine
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    _engine = create_async_engine(url, echo=False, future=True)
    event.listen(_engine.sync_engine, "connect", _on_connect)
    _maker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("engine not initialized; call init_engine() first")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _maker is None:
        raise RuntimeError("engine not initialized; call init_engine() first")
    return _maker


async def dispose_engine() -> None:
    """Close the engine and reset module state."""
    global _engine, _maker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _maker = None
