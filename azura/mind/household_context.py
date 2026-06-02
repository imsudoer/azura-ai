"""Household context: family/roommate/pet color, used to enrich prompts."""
from __future__ import annotations

from azura.personality.schema import Persona


def lines(persona: Persona) -> list[str]:
    """Small set of strings describing the household for prompt injection."""
    out: list[str] = []
    h = persona.household
    if h.lives_with:
        out.append("lives with: " + ", ".join(h.lives_with))
    for fam in h.family or []:
        rel = fam.get("relation") or "relative"
        name = fam.get("name") or "?"
        age = fam.get("age")
        suffix = f", {age}" if age else ""
        out.append(f"{rel}: {name}{suffix}")
    for pet in h.pets or []:
        out.append(f"pet: {pet}")
    if h.home_notes:
        out.append("home: " + h.home_notes)
    return out


def short_one_liner(persona: Persona) -> str:
    """Compact one-liner used in inline prompt snippets."""
    parts = lines(persona)
    return "; ".join(parts[:5])
