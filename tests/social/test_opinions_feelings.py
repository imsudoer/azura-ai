"""Opinion bumps, chat aggregation, proximity."""
from __future__ import annotations

import pytest

from azura.constants import Proximity
from azura.utils.timez import ts
from tests.factories import make_persona

pytestmark = pytest.mark.asyncio


async def test_opinion_bump_clamps(memory, session):
    await memory.repos.users.upsert(101)
    score = await memory.opinions.bump_user(101, 200)
    assert score == 100
    score = await memory.opinions.bump_user(101, -250)
    assert score == -100


async def test_chat_aggregate_balances_members(memory, session):
    await memory.repos.chats.upsert(-1, "supergroup")
    await memory.opinions.bump_chat(-1, 0)
    for uid, delta in ((1, 80), (2, 60), (3, -10)):
        await memory.repos.users.upsert(uid)
        await memory.opinions.bump_user(uid, delta)
    await session.commit()
    agg = await memory.opinions.chat_aggregate(-1, [1, 2, 3])
    assert agg > 0


async def test_proximity_requires_score_and_age(memory, session):
    await memory.repos.users.upsert(101)
    await memory.opinions.bump_user(101, 50)
    await session.commit()
    prox = await memory.opinions.proximity(101)
    assert prox == Proximity.STRANGER
    u = await memory.repos.users.get(101)
    u.first_contact_ts = ts() - 40 * 24 * 3600
    await session.flush()
    prox = await memory.opinions.proximity(101)
    assert prox == Proximity.FRIEND


async def test_feelings_dominant(memory, session):
    await memory.repos.users.upsert(101)
    await memory.feelings.bump_user(101, "fondness", 0.4)
    await memory.feelings.bump_user(101, "annoyance", 0.2)
    await session.commit()
    dom = await memory.feelings.dominant_user(101)
    assert dom is not None
    assert dom[0] == "fondness"


async def test_relationship_symmetric_storage(memory, session):
    await memory.relationships.note(101, 102, kind="friends", strength=0.7)
    await session.commit()
    around = await memory.relationships.around(101)
    assert any(r["other"] == 102 and r["kind"] == "friends" for r in around)
    around = await memory.relationships.around(102)
    assert any(r["other"] == 101 for r in around)
