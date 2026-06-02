"""Dispatcher end-to-end with FakeClient + monkey-patched Agent (no LLM calls)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from azura.config import Settings
from azura.constants import Presence
from azura.db.engine import get_sessionmaker
from azura.db.repo import Repos
from azura.humanize.backpressure import Backpressure
from azura.humanize.style_diversity import StyleDiversity
from azura.memory.service import MemoryService
from azura.mind.agent import AgentResult
from azura.mind.mood import MoodEngine
from azura.mind.presence import PresenceEngine
from azura.telegram.handlers import Dispatcher
from azura.utils.rng import Rng
from tests.factories import make_persona
from tests.integration._fakes import FakeChat, FakeClient, FakeMessage, FakePyrogramChatType, FakeUser

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _zero(*_a, **_k):
        return None
    import asyncio
    monkeypatch.setattr(asyncio, "sleep", _zero)
    import azura.humanize.typing as ht
    monkeypatch.setattr(ht.asyncio, "sleep", _zero)
    import azura.telegram.senders as ts
    monkeypatch.setattr(ts.asyncio, "sleep", _zero)


def _patch_chat_types(monkeypatch):
    import azura.telegram.handlers as h
    monkeypatch.setattr(h, "_TG_KIND", {
        FakePyrogramChatType.PRIVATE: "private",
        FakePyrogramChatType.GROUP: "group",
        FakePyrogramChatType.SUPERGROUP: "supergroup",
        FakePyrogramChatType.CHANNEL: "channel",
        FakePyrogramChatType.BOT: "bot",
    })


def _patch_intent(monkeypatch, decision: str = "reply", score: float = 0.9):
    import azura.telegram.handlers as h
    class _FakeIntent:
        def __init__(self, *a, **kw): ...
        async def decide_reply(self, **_kw):
            from azura.mind.intent import ReplyDecision
            return ReplyDecision(decision=decision, score=score, reason="forced")
    monkeypatch.setattr(h, "IntentEngine", _FakeIntent)


def _patch_agent(monkeypatch, messages: list[str]):
    import azura.telegram.handlers as h
    class _FakeAgent:
        def __init__(self, *a, **kw): ...
        async def run(self, **_kw):
            return AgentResult(messages=messages, actions=[], tool_calls=0)
    monkeypatch.setattr(h, "Agent", _FakeAgent)


async def test_dispatcher_records_and_replies(db, session, persona, monkeypatch):
    _patch_chat_types(monkeypatch)
    _patch_intent(monkeypatch, "reply")
    _patch_agent(monkeypatch, ["hey", "what's up"])

    fake_client = FakeClient(me_id=999, me_username="mira_xx")
    sm = get_sessionmaker()
    settings = Settings(
        TG_API_ID=1, TG_API_HASH="x", OPERATOR_ID=1,
        OPERATOR_SECRET="secret", ONLYSQ_API_KEY="test",
        DB_PATH=db,
    )

    disp = Dispatcher(
        client=fake_client, persona=persona, sessionmaker=sm, settings=settings,
        rng=Rng(1),
        backpressure=Backpressure(global_min_gap_s=0.0, per_chat_max_per_min=999),
        style=StyleDiversity(window=20, n=4),
        mood_engine_factory=lambda p, m, *, rng: MoodEngine(p, m, rng=rng),
        presence_engine_factory=lambda p, m, *, rng: PresenceEngine(p, m, rng=rng),
    )

    async with sm() as s2:
        r = Repos(s2)
        from azura.mind.presence import PresenceEngine as PE
        eng = PE(persona, MemoryService(r), rng=Rng(1))
        await eng.set(Presence.ONLINE, reason="test")
        await s2.commit()

    chat = FakeChat(id=-1, type=FakePyrogramChatType.PRIVATE)
    user = FakeUser(id=101, first_name="Alice", username="alice")
    msg = FakeMessage(id=1, chat=chat, from_user=user, text="hello mira",
                      date=datetime.now(timezone.utc))
    await disp.on_message(fake_client, msg)

    sent = [text for cid, text, _ in fake_client.sent_messages if cid == -1]
    assert len(sent) >= 2

    async with sm() as s2:
        r = Repos(s2)
        recorded = await r.messages.last_n(-1, n=5)
        assert any((m.text or "").startswith("hello") for m in recorded)


async def test_dispatcher_read_only_does_not_send(db, persona, monkeypatch):
    _patch_chat_types(monkeypatch)
    _patch_intent(monkeypatch, "read_only")
    _patch_agent(monkeypatch, ["should not appear"])

    fake_client = FakeClient()
    sm = get_sessionmaker()
    settings = Settings(
        TG_API_ID=1, TG_API_HASH="x", OPERATOR_ID=1,
        OPERATOR_SECRET="secret", ONLYSQ_API_KEY="test", DB_PATH=db,
    )

    disp = Dispatcher(
        client=fake_client, persona=persona, sessionmaker=sm, settings=settings,
        rng=Rng(2),
        backpressure=Backpressure(global_min_gap_s=0.0, per_chat_max_per_min=999),
        style=StyleDiversity(window=20, n=4),
        mood_engine_factory=lambda p, m, *, rng: MoodEngine(p, m, rng=rng),
        presence_engine_factory=lambda p, m, *, rng: PresenceEngine(p, m, rng=rng),
    )

    async with sm() as s2:
        r = Repos(s2)
        eng = PresenceEngine(persona, MemoryService(r), rng=Rng(1))
        await eng.set(Presence.ONLINE, reason="test")
        await s2.commit()

    msg = FakeMessage(id=1, chat=FakeChat(id=-1, type=FakePyrogramChatType.PRIVATE),
                      from_user=FakeUser(id=101, first_name="A"),
                      text="hi", date=datetime.now(timezone.utc))
    await disp.on_message(fake_client, msg)

    assert fake_client.sent_messages == []
    assert -1 in fake_client.read_history_calls


async def test_dispatcher_skips_when_asleep(db, persona, monkeypatch):
    _patch_chat_types(monkeypatch)
    _patch_intent(monkeypatch, "reply")
    _patch_agent(monkeypatch, ["never sent"])

    fake_client = FakeClient()
    sm = get_sessionmaker()
    settings = Settings(
        TG_API_ID=1, TG_API_HASH="x", OPERATOR_ID=1,
        OPERATOR_SECRET="secret", ONLYSQ_API_KEY="test", DB_PATH=db,
    )

    disp = Dispatcher(
        client=fake_client, persona=persona, sessionmaker=sm, settings=settings,
        rng=Rng(3),
        backpressure=Backpressure(global_min_gap_s=0.0, per_chat_max_per_min=999),
        style=StyleDiversity(window=20, n=4),
        mood_engine_factory=lambda p, m, *, rng: MoodEngine(p, m, rng=rng),
        presence_engine_factory=lambda p, m, *, rng: PresenceEngine(p, m, rng=rng),
    )

    async with sm() as s2:
        r = Repos(s2)
        eng = PresenceEngine(persona, MemoryService(r), rng=Rng(1))
        await eng.set(Presence.ASLEEP, reason="night")
        await s2.commit()

    msg = FakeMessage(id=1, chat=FakeChat(id=-1, type=FakePyrogramChatType.PRIVATE),
                      from_user=FakeUser(id=101, first_name="A"),
                      text="wake up", date=datetime.now(timezone.utc))
    await disp.on_message(fake_client, msg)

    assert fake_client.sent_messages == []
