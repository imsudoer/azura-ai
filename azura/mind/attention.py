"""Attention scheduler: which chat to look at next."""
from __future__ import annotations

from dataclasses import dataclass

from azura.constants import ChatKind
from azura.db.repo import Repos
from azura.memory.service import MemoryService
from azura.mind.mood import MoodView
from azura.personality.schema import Persona
from azura.utils.timez import ts


@dataclass
class ChatCandidate:
    """A chat being considered for attention this tick."""
    chat_id: int
    kind: str
    muted: bool
    importance: int
    opinion: int
    unseen: int
    last_seen_ts: int
    score: float
    heat: float = 0.0


_KIND_BONUS = {
    ChatKind.PRIVATE.value: 1.0,
    ChatKind.BOT.value: 0.2,
    ChatKind.GROUP.value: 0.6,
    ChatKind.SUPERGROUP.value: 0.6,
    ChatKind.CHANNEL.value: 0.3,
}


class Attention:
    """Build a ranked queue of chats to read next, in user-specified priority order."""

    def __init__(self, persona: Persona, repos: Repos, memory: MemoryService) -> None:
        self.p = persona
        self.r = repos
        self.m = memory

    async def queue(self, *, mood: MoodView, limit: int = 20) -> list[ChatCandidate]:
        """Return ranked candidates respecting the priority schema."""
        from azura.mind.chat_heat import chat_heat as _heat
        chats = await self.r.chats.all_active()
        candidates: list[ChatCandidate] = []
        for c in chats:
            if c.importance <= -100:
                continue
            unseen = await self.r.messages.unseen_count(c.id)
            heat = await _heat(self.r, c.id)
            if unseen == 0 and heat < 0.05 and c.last_seen_ts and ts() - c.last_seen_ts > 24 * 3600:
                continue
            cand = ChatCandidate(
                chat_id=c.id, kind=c.kind, muted=c.muted, importance=c.importance,
                opinion=c.opinion, unseen=unseen, last_seen_ts=c.last_seen_ts,
                score=0.0, heat=heat,
            )
            cand.score = self._score(cand, mood)
            candidates.append(cand)
        candidates.sort(
            key=lambda x: (self._tier(x), -x.score)
        )
        return candidates[:limit]

    @staticmethod
    def _tier(c: ChatCandidate) -> int:
        """Lower is earlier. Maps schema: private→group/super→channel→muted private→muted group."""
        if not c.muted:
            if c.kind in (ChatKind.PRIVATE.value, ChatKind.BOT.value):
                return 0
            if c.kind in (ChatKind.GROUP.value, ChatKind.SUPERGROUP.value):
                return 1
            if c.kind == ChatKind.CHANNEL.value:
                return 2
        if c.kind in (ChatKind.PRIVATE.value, ChatKind.BOT.value):
            return 3
        return 4

    def _score(self, c: ChatCandidate, mood: MoodView) -> float:
        bonus = _KIND_BONUS.get(c.kind, 0.5)
        unseen_boost = min(1.0, c.unseen / 5.0) * 0.6
        op_boost = max(-1.0, min(1.0, c.opinion / 50.0)) * 0.4
        imp_boost = min(1.0, c.importance / 10.0) * 0.3
        heat_boost = c.heat * 0.5
        mood_pen = 0.0
        if c.kind in (ChatKind.GROUP.value, ChatKind.SUPERGROUP.value):
            mood_pen -= (1 - mood.energy) * 0.3 * (1 - self.p.traits.get("extraversion", 0.5))
        if mood.stress > 0.7 and c.opinion < 0:
            mood_pen -= 0.3
        if mood.fatigue > 0.7:
            mood_pen -= 0.2
        return bonus + unseen_boost + op_boost + imp_boost + heat_boost + mood_pen
