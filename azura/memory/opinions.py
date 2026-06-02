"""Opinions service: per-user/chat/topic score with chat aggregation."""
from __future__ import annotations

from azura.constants import OpinionTarget, PROXIMITY_THRESHOLDS, Proximity
from azura.db.repo import Repos
from azura.utils.timez import ts


class Opinions:
    """Persona's stance toward people, chats and topics."""

    def __init__(self, repos: Repos) -> None:
        self.r = repos

    async def user(self, user_id: int) -> int:
        op = await self.r.opinions.get(OpinionTarget.USER.value, user_id)
        return op.score if op else 0

    async def chat(self, chat_id: int) -> int:
        op = await self.r.opinions.get(OpinionTarget.CHAT.value, chat_id)
        return op.score if op else 0

    async def topic(self, topic: str) -> int:
        op = await self.r.opinions.get(OpinionTarget.TOPIC.value, _topic_id(topic))
        return op.score if op else 0

    async def bump_user(
        self, user_id: int, delta: int, *, tags: list[str] | None = None, reason: str | None = None
    ) -> int:
        op = await self.r.opinions.upsert(
            OpinionTarget.USER.value, user_id, delta=delta, tags=tags, reason=reason
        )
        await self.r.users.adjust_opinion(user_id, delta)
        return op.score

    async def bump_chat(
        self, chat_id: int, delta: int, *, tags: list[str] | None = None, reason: str | None = None
    ) -> int:
        op = await self.r.opinions.upsert(
            OpinionTarget.CHAT.value, chat_id, delta=delta, tags=tags, reason=reason
        )
        await self.r.chats.adjust_opinion(chat_id, delta)
        return op.score

    async def bump_topic(
        self, topic: str, delta: int, *, reason: str | None = None
    ) -> int:
        op = await self.r.opinions.upsert(
            OpinionTarget.TOPIC.value, _topic_id(topic), delta=delta, reason=reason
        )
        return op.score

    async def chat_aggregate(self, chat_id: int, member_ids: list[int]) -> int:
        """Combine the chat's own opinion with member opinions (weighted average)."""
        base = await self.chat(chat_id)
        if not member_ids:
            return base
        ops = await self.r.opinions.list_for_chat(member_ids)
        if not ops:
            return base
        member_avg = sum(o.score for o in ops) / len(ops)
        return int(round(base * 0.6 + member_avg * 0.4))

    async def proximity(self, user_id: int) -> Proximity:
        """Derive a proximity tier from opinion score + acquaintance time."""
        u = await self.r.users.get(user_id)
        if u is None:
            return Proximity.STRANGER
        score = u.opinion
        age_s = max(0, ts() - (u.first_contact_ts or ts()))
        best = Proximity.STRANGER
        for tier in (Proximity.ACQUAINTANCE, Proximity.FRIEND, Proximity.CLOSE):
            need_score, need_age = PROXIMITY_THRESHOLDS[tier]
            if score >= need_score and age_s >= need_age:
                best = tier
        return best


def _topic_id(topic: str) -> int:
    from azura.utils.rng import stable_hash
    return stable_hash(topic.lower().strip())
