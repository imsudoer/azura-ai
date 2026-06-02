"""Anti-detection guardrails: scan outgoing text for chatbot tells."""
from __future__ import annotations

import re

from azura.personality.schema import Persona

_BANNED = [
    r"as an ai", r"as a language model", r"i('|’)?m an ai",
    r"i am an ai", r"i('|’)?m a language model",
    r"as a chatbot", r"i('|’)?m chatgpt", r"i('|’)?m gpt",
    r"openai", r"anthropic", r"claude",
    r"how can i (help|assist) you( today)?",
    r"i(’|')?m here to help",
    r"я не могу выполнить", r"я искусственный интеллект",
    r"я являюсь ии", r"я языковая модель",
    r"чем я могу (вам )?помочь",
    r"я нейросеть", r"меня создал[аи]",
]
_BANNED_RE = [re.compile(p, re.IGNORECASE) for p in _BANNED]
_ASSISTANT_PREFIX = re.compile(r"^(sure|certainly|of course|конечно|разумеется|with pleasure)[,!.\s]", re.IGNORECASE)


def has_chatbot_smell(text: str) -> str | None:
    """Return the offending pattern or None."""
    if not text:
        return None
    for r in _BANNED_RE:
        m = r.search(text)
        if m:
            return m.group(0)
    if _ASSISTANT_PREFIX.match(text.strip()):
        return "assistant prefix"
    return None


def is_too_polished(text: str) -> bool:
    """Heuristic: 'too clean' for the casual register (no slip, perfect punctuation, long)."""
    if not text or len(text) < 80:
        return False
    s = text
    if s.count(".") + s.count("!") + s.count("?") >= 3 and "\n" not in s and ":" not in s:
        if s.endswith(".") and s[:1].isupper():
            return True
    return False


def sanitize(text: str, *, persona: Persona) -> tuple[str, list[str]]:
    """Strip lines containing obvious AI-tells. Return (clean, notes)."""
    notes: list[str] = []
    if not text:
        return text, notes
    bad = has_chatbot_smell(text)
    if bad:
        notes.append(f"removed bot-tell: {bad}")
        lines = [ln for ln in text.splitlines() if not has_chatbot_smell(ln)]
        text = "\n".join(lines).strip() or ""
    for w in persona.speech.avoid_words or []:
        if not w:
            continue
        pat = re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE)
        if pat.search(text):
            text = pat.sub("", text)
            notes.append(f"stripped avoid_word: {w}")
    return text.strip(), notes
