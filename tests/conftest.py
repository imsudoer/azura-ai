"""Shared pytest fixtures: in-memory DB, sessions, persona, RNG."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
import pytest_asyncio

os.environ.setdefault("TG_API_ID", "1")
os.environ.setdefault("TG_API_HASH", "x")
os.environ.setdefault("OPERATOR_ID", "1")
os.environ.setdefault("ONLYSQ_API_KEY", "test")

from azura.db.engine import dispose_engine, get_sessionmaker, init_engine
from azura.db.repo import Repos
from azura.db.schema import init_schema
from azura.memory.service import MemoryService
from azura.utils.rng import Rng
from tests.factories import make_persona


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole session (pytest-asyncio default is function-scoped)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db(tmp_path: Path):
    """Per-test fresh SQLite (file-backed; sqlite-vec needs a real file)."""
    db_path = tmp_path / "test.db"
    init_engine(db_path)
    await init_schema(embed_dim=8)
    yield db_path
    await dispose_engine()


@pytest_asyncio.fixture
async def session(db):
    """Open and close a single AsyncSession for the test."""
    maker = get_sessionmaker()
    async with maker() as s:
        yield s


@pytest_asyncio.fixture
async def repos(session) -> Repos:
    return Repos(session)


@pytest_asyncio.fixture
async def memory(repos) -> MemoryService:
    return MemoryService(repos)


@pytest.fixture
def persona():
    return make_persona()


@pytest.fixture
def rng() -> Rng:
    return Rng(seed=1337)
