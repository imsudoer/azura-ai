"""Typing-action ticker: keeps 'typing...' active in long bursts realistically."""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from azura.config import get_settings


async def type_with_ticks(
    *,
    chat_id: int,
    total_seconds: float,
    keepalive: Callable[[int], Awaitable[None]],
    pause_chance: float = 0.25,
    pause_min_s: float = 0.6,
    pause_max_s: float = 2.4,
) -> None:
    """Send periodic 'typing' actions for total_seconds, with brief realistic pauses."""
    if total_seconds <= 0:
        return
    s = get_settings()
    chunk = max(1.5, s.humanize_typing_chunk_s)
    remaining = total_seconds
    import random
    while remaining > 0:
        slice_s = min(chunk, remaining)
        await keepalive(chat_id)
        await asyncio.sleep(slice_s)
        remaining -= slice_s
        if remaining > 1 and random.random() < pause_chance:
            await asyncio.sleep(random.uniform(pause_min_s, pause_max_s))
            remaining -= 0.3
