"""Trait helpers: derived attachment style / humor / conflict style from numeric traits."""
from __future__ import annotations

from azura.constants import PERSONALITY_TRAITS


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def normalize_traits(raw: dict[str, float]) -> dict[str, float]:
    """Clamp every known trait to [0, 1] and fill missing with 0.5."""
    out: dict[str, float] = {}
    for k in PERSONALITY_TRAITS:
        v = raw.get(k, 0.5)
        out[k] = clamp01(v)
    return out


def derive_attachment(traits: dict[str, float]) -> str:
    """Pick an attachment style label from trait combinations."""
    anx = (traits.get("neuroticism", 0.5) + traits.get("jealousy", 0.5)) / 2
    avoid = (1 - traits.get("agreeableness", 0.5)) * 0.5 + (
        1 - traits.get("extraversion", 0.5)
    ) * 0.5
    if anx > 0.65 and avoid > 0.6:
        return "disorganized"
    if anx > 0.65:
        return "anxious"
    if avoid > 0.65:
        return "avoidant"
    return "secure"


def derive_humor(traits: dict[str, float]) -> str:
    """Pick a humor style label."""
    s = traits.get("sarcasm", 0.5)
    p = traits.get("playfulness", 0.5)
    a = traits.get("aggression", 0.5)
    if s > 0.65 and a > 0.55:
        return "biting"
    if p > 0.7:
        return "playful"
    if s > 0.6:
        return "dry"
    return "warm"


def derive_conflict(traits: dict[str, float]) -> str:
    """Pick a conflict style label (TKI-ish)."""
    dom = traits.get("dominance", 0.5)
    agr = traits.get("agreeableness", 0.5)
    pat = traits.get("patience", 0.5)
    if dom > 0.7 and agr < 0.4:
        return "compete"
    if dom < 0.35 and agr > 0.65:
        return "accommodate"
    if pat > 0.65 and agr > 0.55:
        return "collaborate"
    if pat < 0.35:
        return "avoid"
    return "compromise"


def derive_all(traits: dict[str, float]) -> dict[str, str]:
    return {
        "attachment_style": derive_attachment(traits),
        "humor_style": derive_humor(traits),
        "conflict_style": derive_conflict(traits),
    }
