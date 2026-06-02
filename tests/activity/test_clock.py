"""Clock phases + sleep/work windows."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from azura.mind.clock import seconds_until_wake, snapshot
from tests.factories import make_persona


def _at(h: int, m: int = 0):
    return datetime(2026, 6, 2, h, m, tzinfo=ZoneInfo("Europe/Prague"))


def test_phase_deep_night():
    p = make_persona()
    assert snapshot(p, now=_at(2)).phase == "deep_night"


def test_phase_afternoon():
    p = make_persona()
    assert snapshot(p, now=_at(15)).phase == "afternoon"


def test_work_window():
    p = make_persona()
    s = snapshot(p, now=_at(14))
    assert s.is_work_window is True
    s = snapshot(p, now=_at(22))
    assert s.is_work_window is False


def test_sleep_window_after_midnight():
    p = make_persona()
    s = snapshot(p, now=_at(3))
    assert s.is_sleep_window is True


def test_sleep_window_at_work_is_false():
    p = make_persona()
    s = snapshot(p, now=_at(14))
    assert s.is_sleep_window is False


def test_seconds_until_wake_positive():
    p = make_persona()
    s = seconds_until_wake(p, _at(3))
    assert s > 0
