"""MemoryService facade behavior."""
from __future__ import annotations

import pytest

from azura.constants import Proximity

pytestmark = pytest.mark.asyncio


async def test_recall_about_user_bundle(memory, session):
    await memory.repos.users.upsert(101, username="alice", first_name="Alice")
    await memory.repos.chats.upsert(-1, "private")
    await memory.long.add_fact("alice works at netflix", user_id=101, chat_id=-1)
    await memory.opinions.bump_user(101, 5, reason="ok")
    await memory.feelings.bump_user(101, "fondness", 0.4)
    await session.commit()

    b = await memory.recall_about_user(101)
    assert b["opinion"] == 5
    assert "fondness" in b["feelings"]
    assert b["proximity"] in (Proximity.STRANGER.value, Proximity.ACQUAINTANCE.value)


async def test_recall_chat_short_and_long(memory, session):
    await memory.repos.chats.upsert(-1, "private")
    await memory.short.add(-1, "alice mentioned a song")
    await memory.long.add_fact("alice and bob are friends", chat_id=-1)
    await session.commit()
    rc = await memory.recall_chat(-1)
    assert any("song" in s for s in rc["short"])
    assert any("friends" in s for s in rc["long"])


async def test_feelings_decay_drops_tiny(memory, session):
    await memory.repos.users.upsert(101)
    await memory.feelings.bump_user(101, "annoyance", 0.03, decay_rate=2.0)
    await session.commit()
    f = await memory.repos.feelings.get("user", 101, "annoyance")
    f.updated_ts -= 6 * 3600
    await session.flush()
    removed = await memory.feelings.decay()
    await session.commit()
    assert removed >= 1


async def test_opinion_chat_aggregate_weighted(memory, session):
    await memory.repos.chats.upsert(-1, "supergroup")
    await memory.opinions.bump_chat(-1, 20)
    for uid, delta in ((101, 40), (102, -10), (103, 0)):
        await memory.repos.users.upsert(uid)
        await memory.opinions.bump_user(uid, delta)
    await session.commit()
    agg = await memory.opinions.chat_aggregate(-1, [101, 102, 103])
    assert 5 < agg < 25
