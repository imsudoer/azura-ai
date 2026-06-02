"""ConflictEngine moves by trait combinations."""
from __future__ import annotations

import pytest

from azura.mind.conflict import ConflictEngine
from tests.factories import make_persona

pytestmark = pytest.mark.asyncio


async def test_high_dominance_low_agreeableness_competes(memory, session):
    p = make_persona(traits={"dominance": 0.9, "agreeableness": 0.2, "patience": 0.3,
                             "aggression": 0.7, "loyalty": 0.5, "pettiness": 0.7,
                             "sarcasm": 0.4})
    p.derived["conflict_style"] = "compete"
    await memory.repos.users.upsert(101)
    eng = ConflictEngine(p, memory)
    d = await eng.decide(opponent_id=101, chat_id=None, opponent_aggression=0.6, topic_importance=0.7)
    assert d.move == "escalate"
    assert d.grudge_delta < 0


async def test_high_patience_high_agreeableness_deescalates(memory, session):
    p = make_persona(traits={"patience": 0.9, "agreeableness": 0.9, "aggression": 0.1,
                             "sarcasm": 0.2, "pettiness": 0.1})
    p.derived["conflict_style"] = "collaborate"
    await memory.repos.users.upsert(101)
    eng = ConflictEngine(p, memory)
    d = await eng.decide(opponent_id=101, chat_id=None, opponent_aggression=0.2, topic_importance=0.4)
    assert d.move == "deescalate"


async def test_apply_adjusts_opinion_and_feeling(memory, session):
    p = make_persona(traits={"dominance": 0.9, "agreeableness": 0.2, "patience": 0.3,
                             "aggression": 0.8, "pettiness": 0.6, "sarcasm": 0.3})
    p.derived["conflict_style"] = "compete"
    await memory.repos.users.upsert(101)
    await session.commit()
    eng = ConflictEngine(p, memory)
    d = await eng.decide(opponent_id=101, chat_id=None, opponent_aggression=0.7, topic_importance=0.7)
    await eng.apply(opponent_id=101, decision=d)
    await session.commit()
    op = await memory.opinions.user(101)
    annoy = (await memory.feelings.toward_user(101)).get("annoyance", 0.0)
    assert op < 0
    assert annoy > 0
