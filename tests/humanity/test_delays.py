"""Delay planner shapes."""
from __future__ import annotations

import statistics
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from azura.humanize.delays import reply_delay, split_burst_delays
from azura.mind.clock import snapshot
from azura.mind.mood import MoodView
from azura.utils.rng import Rng
from tests.factories import make_persona


def _mood(**k) -> MoodView:
    base = dict(valence=0.0, arousal=0.4, energy=0.6, focus=0.5, stress=0.3, fatigue=0.3)
    base.update(k)
    return MoodView(**base)


def test_delay_never_below_floor_or_above_ceiling():
    p = make_persona()
    clk = snapshot(p, now=datetime(2026, 6, 2, 14, 0, tzinfo=ZoneInfo("Europe/Prague")))
    rng = Rng(1)
    for _ in range(100):
        d = reply_delay(persona=p, mood=_mood(), clock=clk, rng=rng, text_len=40, urgency=0.1, in_private=True)
        assert d.pre_read_s >= 2.5 - 1e-6
        assert d.pre_read_s <= 900 + 1e-6


def test_delay_distribution_has_spread():
    """Real humans don't reply with constant timing."""
    p = make_persona()
    clk = snapshot(p, now=datetime(2026, 6, 2, 14, 0, tzinfo=ZoneInfo("Europe/Prague")))
    rng = Rng(7)
    samples = [
        reply_delay(persona=p, mood=_mood(), clock=clk, rng=rng, text_len=40, urgency=0.1, in_private=True).pre_read_s
        for _ in range(200)
    ]
    sd = statistics.pstdev(samples)
    assert sd > 0.4, f"too rigid: stdev={sd}"


def test_higher_urgency_shorter_delay():
    p = make_persona()
    clk = snapshot(p, now=datetime(2026, 6, 2, 14, 0, tzinfo=ZoneInfo("Europe/Prague")))
    fast = sum(reply_delay(persona=p, mood=_mood(), clock=clk, rng=Rng(i), text_len=20, urgency=0.9, in_private=True).pre_read_s for i in range(40))
    slow = sum(reply_delay(persona=p, mood=_mood(), clock=clk, rng=Rng(i), text_len=20, urgency=0.0, in_private=True).pre_read_s for i in range(40))
    assert fast < slow


def test_fatigue_increases_delay():
    p = make_persona()
    clk = snapshot(p, now=datetime(2026, 6, 2, 14, 0, tzinfo=ZoneInfo("Europe/Prague")))
    awake = sum(reply_delay(persona=p, mood=_mood(fatigue=0.1), clock=clk, rng=Rng(i), text_len=20, urgency=0.1, in_private=True).pre_read_s for i in range(40))
    tired = sum(reply_delay(persona=p, mood=_mood(fatigue=0.9), clock=clk, rng=Rng(i), text_len=20, urgency=0.1, in_private=True).pre_read_s for i in range(40))
    assert tired > awake


def test_night_slower_than_day():
    p = make_persona()
    rng = Rng(13)
    tz = ZoneInfo("Europe/Prague")
    day = sum(reply_delay(persona=p, mood=_mood(), clock=snapshot(p, now=datetime(2026, 6, 2, 14, 0, tzinfo=tz)), rng=Rng(i), text_len=30, urgency=0.1, in_private=True).pre_read_s for i in range(40))
    night = sum(reply_delay(persona=p, mood=_mood(), clock=snapshot(p, now=datetime(2026, 6, 2, 2, 0, tzinfo=tz)), rng=Rng(i), text_len=30, urgency=0.1, in_private=True).pre_read_s for i in range(40))
    assert night > day


def test_burst_delays_count_and_range():
    rng = Rng(1)
    gaps = split_burst_delays(rng, 4)
    assert len(gaps) == 3
    assert all(0.5 < g < 4.0 for g in gaps)


def test_burst_delays_empty_for_single_message():
    assert split_burst_delays(Rng(1), 1) == []
