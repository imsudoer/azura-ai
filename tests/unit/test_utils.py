"""Utilities: rng, timez, text."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from azura.utils.rng import Rng, stable_hash
from azura.utils.text import contains_name, find_mentions, ngrams, words
from azura.utils.timez import in_window, parse_hhmm, seconds_until


def test_rng_determinism():
    a = Rng(42); b = Rng(42)
    assert [a.randint(0, 100) for _ in range(20)] == [b.randint(0, 100) for _ in range(20)]


def test_rng_chance_bounds():
    r = Rng(1)
    assert r.chance(0.0) is False
    assert r.chance(1.0) is True
    hits = sum(1 for _ in range(5000) if r.chance(0.3))
    assert 1200 < hits < 1800


def test_rng_child_is_independent_but_stable():
    a = Rng(7).child("mood")
    b = Rng(7).child("mood")
    c = Rng(7).child("other")
    assert a.randint(0, 1000) == b.randint(0, 1000)
    assert a.randint(0, 1000) != c.randint(0, 1000)


def test_stable_hash_same_input():
    assert stable_hash("foo") == stable_hash("foo")
    assert stable_hash("foo") != stable_hash("bar")


def test_words_and_ngrams():
    toks = words("Hello, world! Привет, мир.")
    assert "hello" in toks and "мир" in toks
    grams = ngrams(["a", "b", "c", "d"], 2)
    assert grams == [("a", "b"), ("b", "c"), ("c", "d")]


def test_find_mentions():
    assert find_mentions("@alice and @bobby") == ["alice", "bobby"]
    assert find_mentions("no mentions here") == []
    assert find_mentions("@bob too short") == []


def test_contains_name_case_insensitive():
    assert contains_name("Hey MIRA you there", ["Mira"])
    assert not contains_name("nothing", ["Mira"])


def test_parse_hhmm_and_window():
    assert parse_hhmm("09:30").hour == 9
    tz = ZoneInfo("Europe/Prague")
    dt = datetime(2026, 6, 2, 14, 0, tzinfo=tz)
    assert in_window(dt, "10:00", "19:00")
    assert not in_window(dt, "20:00", "23:00")


def test_window_wraps_midnight():
    tz = ZoneInfo("Europe/Prague")
    night = datetime(2026, 6, 2, 3, 0, tzinfo=tz)
    assert in_window(night, "22:00", "04:00")
    morning = datetime(2026, 6, 2, 11, 0, tzinfo=tz)
    assert not in_window(morning, "22:00", "04:00")


def test_seconds_until_future():
    tz = ZoneInfo("Europe/Prague")
    now = datetime(2026, 6, 2, 14, 0, tzinfo=tz)
    s = seconds_until(now, "15:00")
    assert s == 3600
