"""Backpressure: throttle outgoing across chats, prevent simultaneous sends."""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque

from azura.utils.timez import ts


class Backpressure:
    """Single in-flight slot, per-chat rate windows, global cooldown."""

    def __init__(
        self,
        *,
        global_min_gap_s: float = 0.6,
        per_chat_max_per_min: int = 8,
    ) -> None:
        self._lock = asyncio.Lock()
        self._global_last_ts: float = 0.0
        self._global_gap = global_min_gap_s
        self._per_chat: dict[int, deque[int]] = defaultdict(lambda: deque(maxlen=64))
        self._chat_max = per_chat_max_per_min

    async def gate(self, chat_id: int) -> None:
        """Acquire send permission for chat_id; awaits if needed."""
        async with self._lock:
            now_t = ts()
            window_start = now_t - 60
            q = self._per_chat[chat_id]
            while q and q[0] < window_start:
                q.popleft()
            wait_for = 0.0
            if len(q) >= self._chat_max:
                wait_for = max(wait_for, (q[0] + 60) - now_t)
            now_f = asyncio.get_event_loop().time()
            since = now_f - self._global_last_ts
            if since < self._global_gap:
                wait_for = max(wait_for, self._global_gap - since)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._global_last_ts = asyncio.get_event_loop().time()
            self._per_chat[chat_id].append(ts())
