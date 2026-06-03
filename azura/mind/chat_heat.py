"""Chat heat: how 'hot' a conversation is right now.

Heat is 0.0–1.0 representing how actively a chat is being used.
A chat where someone is actively typing back and forth in the last few
minutes is ~0.8–1.0. A chat silent for an hour is ~0.0.

Used by Attention, IntentEngine, Reader, and cooldown to prioritize
active conversations.
"""
from __future__ import annotations

from azura.db.repo import Repos
from azura.utils.timez import ts


async def chat_heat(repos: Repos, chat_id: int) -> float:
    """Compute heat for a single chat. Returns 0.0–1.0."""
    now = ts()

    msgs_5m = await repos.archive.count_since(chat_id, now - 300)
    msgs_15m = await repos.archive.count_since(chat_id, now - 900)

    last_incoming = await repos.archive.last_incoming_ts(chat_id)
    last_self = await repos.archive.last_self_ts(chat_id)

    recency = 0.0
    if last_incoming:
        age_s = max(0, now - last_incoming)
        if age_s < 60:
            recency = 1.0
        elif age_s < 300:
            recency = 1.0 - (age_s - 60) / 240.0
        elif age_s < 900:
            recency = 0.3 * (1.0 - (age_s - 300) / 600.0)

    was_dialoguing = False
    if last_self and last_incoming:
        gap = abs(last_self - last_incoming)
        if gap < 300:
            was_dialoguing = True

    velocity = min(1.0, msgs_5m / 6.0) * 0.5 + min(1.0, msgs_15m / 15.0) * 0.2

    dialog_bonus = 0.2 if was_dialoguing else 0.0

    heat = recency * 0.5 + velocity + dialog_bonus
    return max(0.0, min(1.0, heat))


async def batch_heat(repos: Repos, chat_ids: list[int]) -> dict[int, float]:
    """Compute heat for multiple chats."""
    return {cid: await chat_heat(repos, cid) for cid in chat_ids}
