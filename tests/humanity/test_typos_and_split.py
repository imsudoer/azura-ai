"""Typos + splitter + style diversity."""
from __future__ import annotations

import pytest

from azura.humanize.splitter import split_reply
from azura.humanize.style_diversity import StyleDiversity
from azura.humanize.typos import correction_messages, inject_typos
from azura.utils.rng import Rng
from tests.factories import make_persona


def test_typos_zero_rate_leaves_text():
    out, ts = inject_typos("hello world", rate=0.0, rng=Rng(1))
    assert out == "hello world" and ts == []


def test_typos_high_rate_introduces_changes():
    out, ts = inject_typos("the quick brown fox jumps over the lazy dog", rate=0.8, rng=Rng(2))
    assert ts, "expected at least one typo"
    assert out != "the quick brown fox jumps over the lazy dog"


def test_typos_only_touch_long_words():
    """We must not corrupt single-letter or two-letter tokens."""
    out, ts = inject_typos("a b cd ef", rate=1.0, rng=Rng(3))
    for orig, _new in ts:
        assert len(orig) >= 4


def test_corrections_capped():
    typos = [("alice", "alise"), ("bob", "bok"), ("charlie", "charle"), ("dave", "dabe")]
    out = correction_messages(typos, rng=Rng(1), chance=1.0)
    assert len(out) <= 2


def test_split_respects_multi_chance_zero():
    p = make_persona(speech={"multi_message_chance": 0.0})
    text = "first sentence. second sentence! third sentence?"
    assert split_reply(text, persona=p, rng=Rng(1)) == [text]


def test_split_double_newline_always_splits():
    p = make_persona(speech={"multi_message_chance": 0.0})
    parts = split_reply("hey\n\nyo", persona=p, rng=Rng(1))
    assert parts == ["hey", "yo"]


def test_split_soft_fallback_no_terminators():
    p = make_persona(speech={"multi_message_chance": 1.0, "sentence_length_avg": 5})
    text = "сегодня я пошла на работу и устала потом думала о коте короче день длинный"
    parts = split_reply(text, persona=p, rng=Rng(11))
    assert len(parts) >= 2


def test_style_diversity_repeats_caught():
    sd = StyleDiversity(window=5, n=3)
    sd.add("я устала и пошла домой")
    assert sd.overlap_ratio("я устала и пошла домой") == 1.0
    assert sd.overlap_ratio("купила хлеб в магазине") == 0.0
    assert sd.too_similar("я устала и пошла домой") is True
    assert sd.too_similar("купила хлеб в магазине") is False
