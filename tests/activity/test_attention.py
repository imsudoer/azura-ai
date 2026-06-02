"""Attention queue: priority schema enforced."""
from __future__ import annotations

import pytest

from azura.mind.attention import Attention
from azura.mind.mood import MoodView
from tests.factories import make_persona

pytestmark = pytest.mark.asyncio


def _mood():
    return MoodView(valence=0.0, arousal=0.4, energy=0.6, focus=0.5, stress=0.3, fatigue=0.3)


async def test_priority_schema_order(memory, session):
    p = make_persona()
    for cid, kind, muted in (
        (-1, "private", False),
        (-2, "supergroup", False),
        (-3, "channel", False),
        (-4, "private", True),
        (-5, "supergroup", True),
    ):
        await memory.repos.chats.upsert(cid, kind)
        if muted:
            await memory.repos.chats.set_muted(cid, True)
        await memory.repos.messages.add(chat_id=cid, tg_msg_id=1, from_id=999, ts_=1, text="hi")
    await session.commit()
    att = Attention(p, memory.repos, memory)
    q = await att.queue(mood=_mood(), limit=20)
    ids = [c.chat_id for c in q]
    assert ids.index(-1) < ids.index(-2) < ids.index(-3) < ids.index(-4) < ids.index(-5)


async def test_unseen_boosts_score_within_tier(memory, session):
    p = make_persona()
    await memory.repos.chats.upsert(-10, "private")
    await memory.repos.chats.upsert(-11, "private")
    for mid in range(1, 6):
        await memory.repos.messages.add(chat_id=-10, tg_msg_id=mid, from_id=1, ts_=mid, text="x")
    await memory.repos.messages.add(chat_id=-11, tg_msg_id=1, from_id=1, ts_=1, text="x")
    await session.commit()
    att = Attention(p, memory.repos, memory)
    q = await att.queue(mood=_mood(), limit=20)
    ids = [c.chat_id for c in q]
    assert ids.index(-10) < ids.index(-11)
