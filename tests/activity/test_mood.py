"""MoodEngine: drift toward baseline, nudges, sleep reset."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from azura.mind.clock import snapshot
from azura.mind.mood import MoodEngine, baseline_for
from azura.utils.rng import Rng
from tests.factories import make_persona

pytestmark = pytest.mark.asyncio


def _at(h: int):
    return datetime(2026, 6, 2, h, 0, tzinfo=ZoneInfo("Europe/Prague"))


async def test_baseline_bounded():
    p = make_persona(traits={"agreeableness": 0.9, "neuroticism": 0.1, "extraversion": 0.8})
    b = baseline_for(p)
    assert -1 <= b.valence <= 1
    assert 0 <= b.arousal <= 1


async def test_drift_pulls_toward_baseline(memory, session):
    p = make_persona(traits={"agreeableness": 0.9, "neuroticism": 0.1})
    eng = MoodEngine(p, memory, rng=Rng(1))
    await memory.repos.mood.set(valence=-0.9, arousal=0.0, energy=0.0)
    await session.commit()
    out = await eng.drift(dt_minutes=120, clock=snapshot(p, now=_at(14)))
    assert out.valence > -0.9


async def test_nudge_clamps_valence(memory, session):
    p = make_persona()
    eng = MoodEngine(p, memory, rng=Rng(1))
    out = await eng.nudge(valence=5.0, arousal=2.0, stress=2.0)
    assert out.valence == 1.0
    assert out.arousal == 1.0
    assert out.stress == 1.0


async def test_sleep_reset_lowers_fatigue(memory, session):
    p = make_persona()
    eng = MoodEngine(p, memory, rng=Rng(1))
    await memory.repos.mood.set(fatigue=0.95, stress=0.8)
    await session.commit()
    await eng.sleep_reset()
    cur = await eng.now()
    assert cur.fatigue < 0.5
    assert cur.stress < 0.8
