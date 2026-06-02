"""Intent decisions: reply / silently read / write first / ghost."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from azura.constants import Proximity
from azura.memory.service import MemoryService
from azura.mind.mood import MoodView
from azura.mind.triggers import TriggerHit, urgency
from azura.personality.schema import Persona
from azura.utils.rng import Rng

Decision = Literal["reply", "read_only", "ignore", "react", "later"]


@dataclass
class ReplyDecision:
    """Outcome of decide_reply()."""
    decision: Decision
    score: float
    reason: str


class IntentEngine:
    """Probabilistic decisions about whether to engage with a message."""

    def __init__(self, persona: Persona, memory: MemoryService, *, rng: Rng) -> None:
        self.p = persona
        self.m = memory
        self.rng = rng

    async def decide_reply(
        self,
        *,
        chat_id: int,
        from_user_id: int | None,
        text: str,
        trigger: TriggerHit,
        mood: MoodView,
        in_private: bool,
    ) -> ReplyDecision:
        """Decide what to do about an incoming message."""
        t = self.p.traits
        u_urg = urgency(trigger)
        op_user = 0
        prox = Proximity.STRANGER
        feelings: dict[str, float] = {}
        if from_user_id is not None:
            op_user = await self.m.opinions.user(from_user_id)
            prox = await self.m.opinions.proximity(from_user_id)
            feelings = await self.m.feelings.toward_user(from_user_id)
        op_chat = await self.m.opinions.chat(chat_id)

        base = 0.55 if in_private else 0.22
        base += t["talkativeness"] * 0.20 - (1 - t["social_battery"]) * 0.15
        base += t["extraversion"] * 0.10
        base += u_urg * 0.45
        base += (op_user / 100.0) * 0.20
        base += (op_chat / 100.0) * 0.10
        if prox == Proximity.CLOSE:
            base += 0.20
        elif prox == Proximity.FRIEND:
            base += 0.10
        elif prox == Proximity.STRANGER and not in_private:
            base -= 0.08
        annoy = feelings.get("annoyance", 0.0) + feelings.get("anger", 0.0)
        base -= annoy * 0.30
        fond = feelings.get("fondness", 0.0) + feelings.get("curiosity", 0.0)
        base += fond * 0.15
        base += (mood.valence * 0.10) + (mood.energy - 0.5) * 0.15
        base -= mood.fatigue * 0.20
        base -= mood.stress * 0.10
        if trigger.boundary_hit:
            base -= 0.25

        ghost = self.p.social.ghost_chance + (1 - t["agreeableness"]) * 0.05
        read_only = self.p.social.read_no_reply_chance + max(0.0, mood.fatigue - 0.6) * 0.3
        score = max(0.0, min(1.0, base))

        if self.rng.chance(ghost) and not trigger.reply_to_self and not in_private:
            return ReplyDecision("ignore", score, "ghost")
        if self.rng.chance(read_only) and not trigger.reply_to_self and u_urg < 0.5:
            return ReplyDecision("read_only", score, "read, didn't feel like answering")
        if mood.fatigue > 0.85 and not trigger.reply_to_self:
            return ReplyDecision("later", score, "too tired")
        if self.rng.chance(score):
            return ReplyDecision("reply", score, "engaged")
        if u_urg > 0.3 and self.rng.chance(0.4 + t["playfulness"] * 0.3):
            return ReplyDecision("react", score, "just a reaction")
        return ReplyDecision("read_only", score, "skipped this one")

    async def decide_first_message(
        self,
        *,
        peer_id: int,
        last_contact_age_s: int,
        mood: MoodView,
        clock_evening: bool,
    ) -> ReplyDecision:
        """Decide whether to initiate a chat right now."""
        t = self.p.traits
        prox = await self.m.opinions.proximity(peer_id)
        if prox == Proximity.STRANGER:
            return ReplyDecision("ignore", 0.0, "no reason to message strangers")
        op = await self.m.opinions.user(peer_id)
        gap_h = last_contact_age_s / 3600.0
        miss = min(1.0, gap_h / (24 * 7))
        score = self.p.social.first_message_per_hour
        score += miss * self.p.social.initiate_close_chance * (1.0 if prox == Proximity.CLOSE else 0.5)
        score += t["extraversion"] * 0.10 + t["loyalty"] * 0.08
        score += (op / 100.0) * 0.20
        score += mood.valence * 0.10 + (mood.energy - 0.4) * 0.10
        if clock_evening:
            score += 0.05
        score = max(0.0, min(1.0, score))
        if self.rng.chance(score):
            return ReplyDecision("reply", score, f"missed them ({prox.value})")
        return ReplyDecision("ignore", score, "not now")
