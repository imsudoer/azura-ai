"""Random life events: phone died, went for coffee, weather changed."""
from __future__ import annotations

from dataclasses import dataclass

from azura.memory.service import MemoryService
from azura.mind.presence import PresenceEngine
from azura.personality.schema import Persona
from azura.utils.rng import Rng

EventKind = str


@dataclass
class LifeEvent:
    """A small life happening that affects presence / mood / journal."""
    kind: EventKind
    description: str
    duration_minutes: int


_EVENT_POOL: list[tuple[EventKind, str, int, int]] = [
    ("coffee", "went to make coffee", 4, 12),
    ("shower", "stepped into the shower", 12, 25),
    ("walk", "went for a walk", 20, 60),
    ("store", "ran to the corner store", 15, 35),
    ("dishes", "doing the dishes", 8, 20),
    ("phone_low", "phone is dying, plugging in", 1, 5),
    ("call", "got a phone call", 3, 15),
    ("food", "making something to eat", 10, 25),
    ("nap", "lying down for a bit", 20, 90),
    ("doomscroll", "fell into tiktok", 10, 35),
]


class LifeEventEngine:
    """Roll occasional life events that pull the persona AFK."""

    def __init__(self, persona: Persona, memory: MemoryService, presence: PresenceEngine, *, rng: Rng) -> None:
        self.p = persona
        self.m = memory
        self.presence = presence
        self.rng = rng

    async def maybe_roll(self) -> LifeEvent | None:
        """Per-tick chance to launch an event."""
        chance = 0.03 + 0.05 * self.p.traits.get("impulsivity", 0.5)
        if not self.rng.chance(chance):
            return None
        kind, desc, lo, hi = self.rng.choice(_EVENT_POOL)
        dur = self.rng.randint(lo, hi)
        ev = LifeEvent(kind=kind, description=desc, duration_minutes=dur)
        await self.presence.go_afk(dur, ev.description)
        await self.m.repos.journal.write(ev.description, kind="life_event")
        return ev
