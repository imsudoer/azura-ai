"""Repos + FTS5 + sqlite-vec round-trip."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_chats_upsert_and_mute(repos):
    c = await repos.chats.upsert(-1, "private", title="me")
    assert c.id == -1 and c.kind == "private"
    await repos.chats.set_muted(-1, True)
    c2 = await repos.chats.get(-1)
    assert c2.muted is True


async def test_users_upsert_and_opinion(repos):
    u = await repos.users.upsert(101, username="alice", first_name="Alice")
    assert u.opinion == 0
    score = await repos.users.adjust_opinion(101, 10)
    assert score == 10
    score = await repos.users.adjust_opinion(101, -50)
    assert score == -40


async def test_opinion_score_clamped(repos):
    await repos.users.upsert(1)
    s = await repos.users.adjust_opinion(1, 999)
    assert s == 100
    s = await repos.users.adjust_opinion(1, -9999)
    assert s == -100


async def test_messages_unique_and_search(repos, session):
    await repos.chats.upsert(-1, "private")
    await repos.users.upsert(101)
    m1 = await repos.messages.add(chat_id=-1, tg_msg_id=1, from_id=101, ts_=1, text="hello world cats")
    m2 = await repos.messages.add(chat_id=-1, tg_msg_id=1, from_id=101, ts_=1, text="duplicate")
    assert m1.id == m2.id
    await session.commit()


async def test_memory_fts_and_vec(memory, session):
    await memory.repos.chats.upsert(-1, "private")
    await memory.long.add_fact("alice loves cats", chat_id=-1, embedding=[0.1] * 8)
    await memory.long.add_fact("bob hates dogs", chat_id=-1, embedding=[0.2] * 8)
    await session.commit()
    hits = await memory.long.search("cats")
    assert any("cats" in h for h in hits)
    vec_hits = await memory.long.search_vec([0.1] * 8, k=2)
    assert vec_hits and "cats" in vec_hits[0]


async def test_fts_quote_handles_user_colon(memory, session):
    """User-typed colons must not crash FTS5 column syntax."""
    await memory.long.add_fact("works at netflix")
    await session.commit()
    hits = await memory.long.search("user:101 cats:test")
    assert hits == [] or any("netflix" in h for h in hits)


async def test_opinions_clamped(repos):
    op = await repos.opinions.upsert("user", 1, delta=999)
    assert op.score == 100
    op = await repos.opinions.upsert("user", 1, delta=-9999)
    assert op.score == -100


async def test_kv_json_roundtrip(repos):
    await repos.kv.set_json("k", {"a": 1, "b": [1, 2, 3]})
    assert await repos.kv.get_json("k") == {"a": 1, "b": [1, 2, 3]}
    await repos.kv.delete("k")
    assert await repos.kv.get_json("k") is None
