"""Watch incoming `UpdateUserTyping` / `UpdateChatUserTyping` raw updates.

Records that a user started typing in a chat at time T. When the typing stops
without a message arriving within `expire_s` seconds, fires an `on_orphan_typing`
callback so the persona can react ("ты там чё, передумал?").

If a real message from that user lands first, the entry is cleared silently.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from azura.utils.log import get_logger

log = get_logger("tg.typing_watcher")


@dataclass
class _TypingState:
    started_at: float
    last_seen: float
    chat_id: int
    user_id: int


OrphanCallback = Callable[[int, int, float], Awaitable[None]]
StartCallback = Callable[[int, int], Awaitable[None]]


class TypingWatcher:
    """Track who is typing to whom, fire orphan callback on aborted typings."""

    def __init__(
        self,
        *,
        on_typing_start: StartCallback | None = None,
        on_orphan_typing: OrphanCallback | None = None,
        expire_s: float = 12.0,
        min_orphan_duration_s: float = 3.0,
        tick_s: float = 2.0,
    ) -> None:
        self.on_start = on_typing_start
        self.on_orphan = on_orphan_typing
        self.expire_s = expire_s
        self.min_orphan_duration_s = min_orphan_duration_s
        self.tick_s = tick_s
        self._states: dict[tuple[int, int], _TypingState] = {}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="typing_watcher")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except BaseException:
                pass
            self._task = None

    def note_typing(self, chat_id: int, user_id: int) -> None:
        """Mark that user_id is currently typing in chat_id (called on each raw event)."""
        now = time.monotonic()
        key = (chat_id, user_id)
        st = self._states.get(key)
        if st is None:
            st = _TypingState(started_at=now, last_seen=now, chat_id=chat_id, user_id=user_id)
            self._states[key] = st
            log.debug("typing started chat={} user={}", chat_id, user_id)
            if self.on_start is not None:
                asyncio.create_task(self._fire_start(chat_id, user_id))
        else:
            st.last_seen = now

    def clear(self, chat_id: int, user_id: int) -> None:
        """Drop the entry silently (e.g. a real message arrived)."""
        self._states.pop((chat_id, user_id), None)

    async def _fire_start(self, chat_id: int, user_id: int) -> None:
        try:
            await self.on_start(chat_id, user_id)  # type: ignore[misc]
        except Exception:
            log.exception("on_typing_start failed")

    async def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await self._check_orphans()
                except Exception:
                    log.exception("typing watcher tick failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.tick_s)
                    return
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def _check_orphans(self) -> None:
        now = time.monotonic()
        stale: list[tuple[int, int]] = []
        for key, st in list(self._states.items()):
            if now - st.last_seen >= self.expire_s:
                stale.append(key)
        for key in stale:
            st = self._states.pop(key, None)
            if st is None:
                continue
            duration = st.last_seen - st.started_at
            if duration < self.min_orphan_duration_s:
                continue
            if self.on_orphan is None:
                continue
            try:
                await self.on_orphan(st.chat_id, st.user_id, duration)
            except Exception:
                log.exception("on_orphan_typing failed")
