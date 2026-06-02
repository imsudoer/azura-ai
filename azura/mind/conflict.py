"""Conflict dynamics: escalate, deescalate, side with someone, hold a grudge."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from azura.memory.service import MemoryService
from azura.personality.schema import Persona

ConflictMove = Literal["deescalate", "stand_ground", "escalate", "withdraw", "side_with", "passive_aggressive"]


@dataclass
class ConflictDecision:
    """Conflict outcome for a given exchange."""
    move: ConflictMove
    intensity: float
    grudge_delta: int
    reason: str


class ConflictEngine:
    """Pick a conflict move based on personality traits and social context."""

    def __init__(self, persona: Persona, memory: MemoryService) -> None:
        self.p = persona
        self.m = memory

    async def decide(
        self,
        *,
        opponent_id: int,
        chat_id: int | None,
        opponent_aggression: float,
        topic_importance: float,
    ) -> ConflictDecision:
        t = self.p.traits
        op = await self.m.opinions.user(opponent_id)
        style = self.p.derived.get("conflict_style", "compromise")
        aggression = t["aggression"] + opponent_aggression * 0.3
        patience = t["patience"] - opponent_aggression * 0.2
        pettiness = t["pettiness"]
        loyalty = t["loyalty"]

        if patience > 0.7 and aggression < 0.4:
            move: ConflictMove = "deescalate"
        elif style == "compete" and aggression > 0.55:
            move = "escalate"
        elif style == "avoid":
            move = "withdraw"
        elif style == "accommodate" and op > 0:
            move = "deescalate"
        elif t["passive_aggressive" if "passive_aggressive" in t else "sarcasm"] > 0.6:
            move = "passive_aggressive"
        elif loyalty > 0.6 and chat_id is not None and op > 10:
            move = "side_with"
        elif aggression > patience:
            move = "stand_ground"
        else:
            move = "deescalate"

        intensity = max(0.0, min(1.0, aggression * 0.5 + topic_importance * 0.5))
        grudge = 0
        if move == "escalate":
            grudge = -int(round(2 + pettiness * 5))
        elif move == "passive_aggressive":
            grudge = -int(round(1 + pettiness * 3))
        elif move == "deescalate" and op > 0:
            grudge = 1
        return ConflictDecision(
            move=move, intensity=intensity, grudge_delta=grudge,
            reason=f"style={style}, agr={aggression:.2f}, pat={patience:.2f}",
        )

    async def apply(self, *, opponent_id: int, decision: ConflictDecision) -> None:
        """Persist the decision: bump opinion and possibly mute a grudge feeling."""
        if decision.grudge_delta:
            await self.m.opinions.bump_user(
                opponent_id, decision.grudge_delta, reason=decision.reason
            )
        if decision.move in ("escalate", "passive_aggressive"):
            await self.m.feelings.bump_user(opponent_id, "annoyance", delta=0.2 * decision.intensity)
        elif decision.move == "deescalate":
            await self.m.feelings.bump_user(opponent_id, "fondness", delta=0.05)
