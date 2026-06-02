"""Split long replies into 1-N short messages, with persona-aware probability."""
from __future__ import annotations

import re

from azura.personality.schema import Persona
from azura.utils.rng import Rng

_SENT_RE = re.compile(r"(?<=[.!?…])\s+|\n+", re.UNICODE)
_SOFT_RE = re.compile(r",\s+| и | а | но | потом | короче | вот | ну | так | то есть ", re.IGNORECASE)


def _soft_split(text: str, avg_words: int) -> list[str]:
    """Cheap soft splitter when no hard punctuation exists."""
    parts = [p.strip() for p in _SOFT_RE.split(text) if p and p.strip()]
    out: list[str] = []
    buf: list[str] = []
    for p in parts:
        buf.append(p)
        if sum(len(x.split()) for x in buf) >= avg_words:
            out.append(" ".join(buf))
            buf = []
    if buf:
        out.append(" ".join(buf))
    return out


def split_reply(text: str, *, persona: Persona, rng: Rng, hard_max: int = 5) -> list[str]:
    """Maybe split a single reply into multiple short messages."""
    text = (text or "").strip()
    if not text:
        return []
    if "\n\n" in text:
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        return parts[:hard_max]
    multi_chance = persona.speech.multi_message_chance
    avg_words = max(3, persona.speech.sentence_length_avg)
    sents = [s.strip() for s in _SENT_RE.split(text) if s.strip()]
    if len(sents) <= 1 and len(text.split()) > avg_words * 2:
        chunks2 = _soft_split(text, avg_words)
        if len(chunks2) > 1:
            sents = chunks2
    if len(sents) <= 1:
        return [text]
    if not rng.chance(multi_chance):
        return [text]
    n_target = min(hard_max, max(2, len(sents) // 2 + rng.randint(0, 1)))
    chunks: list[list[str]] = [[] for _ in range(n_target)]
    for i, s in enumerate(sents):
        chunks[i % n_target].append(s)
    out = [" ".join(c).strip() for c in chunks if c]
    out = [_loosen(o, persona, rng, avg_words) for o in out if o]
    return out[:hard_max]


def _loosen(s: str, persona: Persona, rng: Rng, avg_words: int) -> str:
    """Soften punctuation if persona writes loose."""
    if persona.speech.punctuation == "strict":
        return s
    if rng.chance(0.5):
        s = s.rstrip(".")
    if persona.speech.punctuation == "messy" and rng.chance(0.2):
        s = s.replace(", ", " ").replace(". ", " ")
    if rng.chance(0.4) and s[:1].isupper() and persona.speech.register in ("casual", "slangy"):
        s = s[0].lower() + s[1:]
    return s
