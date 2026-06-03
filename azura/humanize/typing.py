"""Typing-action ticker: keeps 'typing...' active in long bursts realistically.

The ticker re-emits the typing chat action every few seconds (Telegram drops
the indicator after ~5s) and, importantly, INTERRUPTS the indicator with
realistic pauses for long messages. A real person rarely types a 200+ char
message without at least one pause to think / reread / fix something — so for
long bursts we go into a 1-4s silent gap during which `typing…` disappears
from the recipient's chat header. ~80% of long messages get at least one
interruption.
"""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable

from azura.config import get_settings


async def type_with_ticks(
    *,
    chat_id: int,
    total_seconds: float,
    keepalive: Callable[[int], Awaitable[None]],
    pause_chance: float | None = None,
    pause_min_s: float = 1.0,
    pause_max_s: float = 4.0,
) -> None:
    """Stream realistic typing pings over `total_seconds`.

    Anatomy of one tick:
      * emit typing keepalive;
      * sleep `chunk` seconds (Telegram shows “typing…” during this);
      * sometimes (more often for long messages) take an "interruption":
        sleep 1–4s WITHOUT re-emitting keepalive so the indicator drops.

    The probability of an interruption per chunk scales with the total
    message length so that long messages reliably get 1-3 pauses while short
    bursts (< ~3s) rarely have any.
    """
    if total_seconds <= 0:
        return
    s = get_settings()
    chunk = max(1.5, s.humanize_typing_chunk_s)

    if pause_chance is None:
        if total_seconds < 3.5:
            pause_chance = 0.05
        elif total_seconds < 7.0:
            pause_chance = 0.30
        elif total_seconds < 12.0:
            pause_chance = 0.55
        else:
            pause_chance = 0.75

    target_breaks_long = 0
    if total_seconds >= 6.0:
        if random.random() < 0.80:
            target_breaks_long = random.choice([1, 1, 2, 2, 3])

    remaining = total_seconds
    breaks_done = 0
    while remaining > 0:
        slice_s = min(chunk, remaining)
        await keepalive(chat_id)
        await asyncio.sleep(slice_s)
        remaining -= slice_s
        if remaining <= 0.4:
            break
        need_forced = breaks_done < target_breaks_long and remaining > 1.5
        if need_forced or random.random() < pause_chance:
            gap = random.uniform(pause_min_s, pause_max_s)
            await asyncio.sleep(gap)
            remaining -= gap * 0.4
            breaks_done += 1
