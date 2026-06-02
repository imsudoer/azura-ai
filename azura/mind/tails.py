"""Conversation tails: 'and one more thing 40 minutes later'."""
from __future__ import annotations

from dataclasses import dataclass

from azura.memory.service import MemoryService
from azura.personality.schema import Persona
from azura.utils.rng import Rng
from azura.utils.timez import ts


@dataclass
class TailDraft:
    """A pending follow-up message."""
    chat_id: int
    text: str
    due_ts: int


class TailQueue:
    """In-memory queue of delayed follow-ups."""

    def __init__(self, persona: Persona, memory: MemoryService | None = None, *, rng: Rng) -> None:
        self.p = persona
        self.m = memory
        self.rng = rng
        self._items: list[TailDraft] = []

    def schedule(self, chat_id: int, text: str, delay_min: float, delay_max: float) -> TailDraft:
        delay = self.rng.uniform(delay_min, delay_max)
        item = TailDraft(chat_id=chat_id, text=text, due_ts=ts() + int(delay))
        self._items.append(item)
        return item

    def due(self) -> list[TailDraft]:
        now = ts()
        ready = [x for x in self._items if x.due_ts <= now]
        self._items = [x for x in self._items if x.due_ts > now]
        return ready

    def maybe_random_tail(self, chat_id: int) -> bool:
        """Random chance to schedule a generic 'oh, also' tail."""
        if self.rng.chance(0.04 * self.p.traits.get("talkativeness", 0.5)):
            self.schedule(chat_id, "", 15 * 60, 90 * 60)
            return True
        return False

    def pending(self) -> int:
        return len(self._items)
