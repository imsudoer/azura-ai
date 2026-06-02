"""Feelings service: time-decaying emotional states toward targets."""
from __future__ import annotations

from azura.constants import FeelingTarget
from azura.db.repo import Repos


class Feelings:
    """How the persona currently feels about a user or a chat."""

    def __init__(self, repos: Repos) -> None:
        self.r = repos

    async def toward_user(self, user_id: int) -> dict[str, float]:
        items = await self.r.feelings.list_for(FeelingTarget.USER.value, user_id)
        return {f.emotion: f.intensity for f in items}

    async def toward_chat(self, chat_id: int) -> dict[str, float]:
        items = await self.r.feelings.list_for(FeelingTarget.CHAT.value, chat_id)
        return {f.emotion: f.intensity for f in items}

    async def bump_user(
        self, user_id: int, emotion: str, delta: float = 0.1, *, decay_rate: float = 0.05, reason: str | None = None
    ) -> float:
        f = await self.r.feelings.bump(
            FeelingTarget.USER.value, user_id, emotion, delta=delta, decay_rate=decay_rate, reason=reason
        )
        return f.intensity

    async def bump_chat(
        self, chat_id: int, emotion: str, delta: float = 0.1, *, decay_rate: float = 0.05, reason: str | None = None
    ) -> float:
        f = await self.r.feelings.bump(
            FeelingTarget.CHAT.value, chat_id, emotion, delta=delta, decay_rate=decay_rate, reason=reason
        )
        return f.intensity

    async def decay(self) -> int:
        """Apply exponential decay to all feelings; called by the scheduler."""
        return await self.r.feelings.decay_step()

    async def dominant_user(self, user_id: int) -> tuple[str, float] | None:
        items = await self.r.feelings.list_for(FeelingTarget.USER.value, user_id)
        if not items:
            return None
        top = max(items, key=lambda f: f.intensity)
        return (top.emotion, top.intensity)
