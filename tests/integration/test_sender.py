"""Sender: full humanize pipeline against a FakeClient."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from azura.humanize.backpressure import Backpressure
from azura.humanize.style_diversity import StyleDiversity
from azura.mind.clock import snapshot
from azura.mind.mood import MoodView
from azura.telegram.senders import Sender
from azura.utils.rng import Rng
from tests.factories import make_persona
from tests.integration._fakes import FakeClient

pytestmark = pytest.mark.asyncio


def _mood():
    return MoodView(valence=0.1, arousal=0.4, energy=0.6, focus=0.5, stress=0.2, fatigue=0.2)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Crush asyncio.sleep calls in humanize modules so tests run fast."""
    async def _zero(*_a, **_k):
        return None
    import asyncio
    monkeypatch.setattr(asyncio, "sleep", _zero)
    import azura.humanize.typing as ht
    monkeypatch.setattr(ht.asyncio, "sleep", _zero)
    import azura.telegram.senders as ts
    monkeypatch.setattr(ts.asyncio, "sleep", _zero)


async def test_sender_sends_and_reads(memory, session, persona):
    fc = FakeClient()
    sender = Sender(
        fc, persona=persona, memory=memory, rng=Rng(1),
        backpressure=Backpressure(global_min_gap_s=0.0, per_chat_max_per_min=999),
        style=StyleDiversity(window=10, n=4),
    )
    clk = snapshot(persona, now=datetime(2026, 6, 2, 14, 0, tzinfo=ZoneInfo("Europe/Prague")))
    res = await sender.send(-1, ["short reply"], mood=_mood(), clock=clk, in_private=True)
    assert res.sent >= 1
    assert any(text == "short reply" or "short reply" in text for _, text, _ in fc.sent_messages)
    assert -1 in fc.read_history_calls


async def test_sender_blocks_chatbot_phrase(memory, session, persona):
    fc = FakeClient()
    sender = Sender(
        fc, persona=persona, memory=memory, rng=Rng(1),
        backpressure=Backpressure(global_min_gap_s=0.0, per_chat_max_per_min=999),
        style=StyleDiversity(window=10, n=4),
    )
    clk = snapshot(persona, now=datetime(2026, 6, 2, 14, 0, tzinfo=ZoneInfo("Europe/Prague")))
    res = await sender.send(-1, ["As an AI language model I cannot help"], mood=_mood(), clock=clk, in_private=True)
    assert res.sent == 0
    assert all("AI" not in text for _, text, _ in fc.sent_messages)


async def test_sender_splits_long_burst(memory, session):
    persona = make_persona(speech={"multi_message_chance": 1.0, "sentence_length_avg": 6, "typos_rate": 0.0, "self_correction_chance": 0.0})
    fc = FakeClient()
    sender = Sender(
        fc, persona=persona, memory=memory, rng=Rng(5),
        backpressure=Backpressure(global_min_gap_s=0.0, per_chat_max_per_min=999),
        style=StyleDiversity(window=10, n=4),
    )
    clk = snapshot(persona, now=datetime(2026, 6, 2, 14, 0, tzinfo=ZoneInfo("Europe/Prague")))
    text = "first sentence here. second one. third one too! fourth and final part."
    await sender.send(-1, [text], mood=_mood(), clock=clk, in_private=True)
    assert len([m for m in fc.sent_messages if m[0] == -1]) >= 2
