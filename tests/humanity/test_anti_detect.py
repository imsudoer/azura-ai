"""Anti-detect filter must catch chatbot tells in ru/en and avoid_words."""
from __future__ import annotations

import pytest

from azura.humanize.anti_detect import has_chatbot_smell, sanitize
from tests.factories import make_persona


@pytest.mark.parametrize("bad", [
    "As an AI language model, I can",
    "i'm a language model trained by openai",
    "How can I help you today?",
    "Я искусственный интеллект.",
    "Я нейросеть, помогаю с вопросами",
    "чем я могу вам помочь?",
    "Sure! Here is the answer:",
    "Конечно, помогу с этим.",
])
def test_chatbot_tells_caught(bad):
    assert has_chatbot_smell(bad) is not None


@pytest.mark.parametrize("ok", [
    "привет, как дела?",
    "ну такое",
    "i'm tired, going to bed",
    "только что вышла из душа",
])
def test_normal_text_passes(ok):
    assert has_chatbot_smell(ok) is None


def test_sanitize_removes_avoid_words():
    p = make_persona(speech={"avoid_words": ["зайка", "солнышко"]})
    out, notes = sanitize("привет зайка, как ты?", persona=p)
    assert "зайка" not in out
    assert any("zайка" in n.lower() or "зайка" in n.lower() for n in notes)


def test_sanitize_strips_assistant_prefix():
    p = make_persona()
    out, notes = sanitize("Sure! I can help.\nReal sentence here.", persona=p)
    assert "Sure" not in out.split("\n")[0]
    assert any("bot-tell" in n for n in notes)
