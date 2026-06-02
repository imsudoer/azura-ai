"""Intent + Triggers behavior on synthetic inputs."""
from __future__ import annotations

import pytest

from azura.mind.intent import IntentEngine
from azura.mind.mood import MoodView
from azura.mind.triggers import detect, urgency
from azura.utils.rng import Rng
from tests.factories import make_persona

asyncio_mark = pytest.mark.asyncio


def _mood(**k):
    base = dict(valence=0.0, arousal=0.4, energy=0.6, focus=0.5, stress=0.3, fatigue=0.3)
    base.update(k)
    return MoodView(**base)


def test_name_triggers_urgency():
    p = make_persona()
    hit = detect(persona=p, text="Mira are you there", own_username="m_x", reply_to_self=False)
    assert hit.name_called
    assert urgency(hit) > 0.3


def test_reply_to_self_dominates():
    p = make_persona()
    hit = detect(persona=p, text="ok", own_username="m_x", reply_to_self=True)
    assert urgency(hit) >= 0.6


def test_boundary_hit_caught():
    p = make_persona()
    hit = detect(persona=p, text="ты такая fake", own_username="m_x", reply_to_self=False)
    assert hit.boundary_hit == "fake"


@asyncio_mark
async def test_private_friendly_replies_more_than_group_stranger(memory, session):
    p = make_persona(traits={"talkativeness": 0.7, "social_battery": 0.7, "extraversion": 0.7})
    eng = IntentEngine(p, memory, rng=Rng(123))
    await memory.repos.users.upsert(101)
    await memory.opinions.bump_user(101, 50)
    await session.commit()
    hit = detect(persona=p, text="hi", own_username="m", reply_to_self=False)
    replies = 0
    for s in range(60):
        e = IntentEngine(p, memory, rng=Rng(s))
        d = await e.decide_reply(chat_id=-1, from_user_id=101, text="hi", trigger=hit, mood=_mood(), in_private=True)
        if d.decision == "reply":
            replies += 1
    assert replies >= 25


@asyncio_mark
async def test_strong_annoyance_lowers_reply(memory, session):
    p = make_persona()
    await memory.repos.users.upsert(101)
    await memory.feelings.bump_user(101, "annoyance", 0.9, decay_rate=0.0)
    await session.commit()
    hit = detect(persona=p, text="hey", own_username="m", reply_to_self=False)
    replies = 0
    for s in range(60):
        e = IntentEngine(p, memory, rng=Rng(s))
        d = await e.decide_reply(chat_id=-1, from_user_id=101, text="hey", trigger=hit, mood=_mood(), in_private=True)
        if d.decision == "reply":
            replies += 1
    assert replies < 35


@asyncio_mark
async def test_fatigue_pushes_later_or_read_only(memory, session):
    p = make_persona()
    hit = detect(persona=p, text="ok", own_username="m", reply_to_self=False)
    eng = IntentEngine(p, memory, rng=Rng(0))
    d = await eng.decide_reply(chat_id=-1, from_user_id=None, text="ok", trigger=hit, mood=_mood(fatigue=0.95), in_private=True)
    assert d.decision in ("later", "read_only", "ignore")
