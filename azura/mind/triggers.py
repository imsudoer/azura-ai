"""Detect attention triggers in incoming messages."""
from __future__ import annotations

from dataclasses import dataclass

from azura.personality.schema import Persona
from azura.utils.text import contains_name, find_mentions


@dataclass
class TriggerHit:
    """Result of trigger detection on a single message."""
    name_called: bool
    username_mentioned: bool
    reply_to_self: bool
    keyword: str | None
    boundary_hit: str | None


def name_variants(persona: Persona) -> list[str]:
    """Possible spellings of the persona's name to scan for."""
    nm = persona.identity.name
    out = {nm, nm.lower()}
    if " " in nm:
        out.add(nm.split()[0])
    return [x for x in out if x]


def detect(
    *,
    persona: Persona,
    text: str,
    own_username: str | None,
    reply_to_self: bool,
    interests: list[str] | None = None,
) -> TriggerHit:
    """Detect triggers in a single message."""
    text = text or ""
    name_called = contains_name(text, name_variants(persona))
    ats = find_mentions(text)
    username_mentioned = bool(own_username) and any(
        m.lower() == own_username.lower() for m in ats
    )
    low = text.lower()
    keyword = None
    for kw in interests or persona.interests:
        if kw and kw.lower() in low:
            keyword = kw
            break
    boundary = None
    for b in persona.boundaries.triggers or []:
        if b and b.lower() in low:
            boundary = b
            break
    return TriggerHit(
        name_called=name_called,
        username_mentioned=username_mentioned,
        reply_to_self=reply_to_self,
        keyword=keyword,
        boundary_hit=boundary,
    )


def urgency(hit: TriggerHit) -> float:
    """Convert triggers into a 0..1 urgency score for attention/intent."""
    score = 0.0
    if hit.reply_to_self:
        score += 0.6
    if hit.name_called:
        score += 0.45
    if hit.username_mentioned:
        score += 0.35
    if hit.keyword:
        score += 0.15
    if hit.boundary_hit:
        score += 0.4
    return min(1.0, score)
