"""PresenceEngine: auto-sleep, wakeup chance, AFK round-trip."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from azura.constants import Presence
from azura.mind.clock import snapshot
from azura.mind.presence import PresenceEngine
from azura.utils.rng import Rng
from tests.factories import make_persona

pytestmark = pytest.mark.asyncio


def _at(h: int):
    return datetime(2026, 6, 2, h, 0, tzinfo=ZoneInfo("Europe/Prague"))


async def test_initial_presence_offline(memory, session):
    eng = PresenceEngine(make_persona(), memory, rng=Rng(1))
    cur = await eng.current()
    await session.commit()
    assert cur.state == Presence.OFFLINE


async def test_sleeps_at_night(memory, session):
    p = make_persona()
    eng = PresenceEngine(p, memory, rng=Rng(1))
    await eng.set(Presence.ONLINE, reason="setup")
    await session.commit()
    cur = await eng.tick(clock=snapshot(p, now=_at(3)), fatigue=0.4)
    await session.commit()
    assert cur.state == Presence.ASLEEP


async def test_wakes_at_morning(memory, session):
    p = make_persona()
    eng = PresenceEngine(p, memory, rng=Rng(2))
    await eng.set(Presence.ASLEEP, reason="setup")
    await session.commit()
    cur = await eng.tick(clock=snapshot(p, now=_at(11)), fatigue=0.1)
    await session.commit()
    assert cur.state == Presence.ONLINE


async def test_afk_roundtrip(memory, session):
    eng = PresenceEngine(make_persona(), memory, rng=Rng(3))
    v = await eng.go_afk(minutes=5, reason="coffee")
    assert v.state == Presence.AFK
    back = await eng.come_back()
    assert back.state == Presence.ONLINE


async def test_busy_during_work(memory, session):
    p = make_persona(traits={"conscientiousness": 1.0})
    eng = PresenceEngine(p, memory, rng=Rng(0))
    await eng.set(Presence.ONLINE, reason="x")
    await session.commit()
    states = []
    for seed in range(40):
        e = PresenceEngine(p, memory, rng=Rng(seed))
        await e.set(Presence.ONLINE, reason="x")
        cur = await e.tick(clock=snapshot(p, now=_at(14)), fatigue=0.2)
        states.append(cur.state)
    assert Presence.BUSY in states
