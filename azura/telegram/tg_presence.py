"""Telegram-visible online status: offline-by-default, brief online windows.

Internal `Presence` (asleep / online / afk / busy) is for behaviour logic.
What other Telegram users SEE is a separate concern: account.updateStatus.

Strategy here: keep Telegram status OFFLINE by default. Only flip to ONLINE
for short windows around real actions (reading, typing, sending). After a
short tail (`online_tail_s`) the keeper re-asserts offline.
"""
from __future__ import annotations

import asyncio
import time

from pyrogram import Client
from pyrogram.raw.functions.account import UpdateStatus

from azura.utils.log import get_logger

log = get_logger("tg.presence")


_state_lock = asyncio.Lock()
_online_until: float = 0.0
_last_pushed: bool | None = None  # None = unknown, True = currently offline, False = online


async def _push(client: Client, offline: bool) -> None:
    global _last_pushed
    try:
        await client.invoke(UpdateStatus(offline=offline))
        if _last_pushed != offline:
            log.info("tg status -> {}", "offline" if offline else "online")
        _last_pushed = offline
    except Exception as e:
        log.warning("UpdateStatus(offline={}) failed: {}", offline, e)


async def go_online_briefly(client: Client, *, seconds: float = 45.0) -> None:
    """Mark Telegram online; auto-offline scheduled `seconds` later."""
    global _online_until
    if client is None:
        return
    async with _state_lock:
        _online_until = max(_online_until, time.monotonic() + seconds)
        await _push(client, offline=False)


async def force_offline(client: Client) -> None:
    """Force offline immediately and clear the online window."""
    global _online_until
    if client is None:
        return
    async with _state_lock:
        _online_until = 0.0
        await _push(client, offline=True)


class PresenceKeeper:
    """Background loop that re-asserts the desired Telegram visibility.

    Behaviour: every `interval_s` checks if we're past the online window
    and (re-)asserts offline. While in an online window it does nothing
    (the per-action `go_online_briefly` already set offline=False).
    """

    def __init__(self, client: Client, *, interval_s: float = 20.0) -> None:
        self.c = client
        self.interval = interval_s
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="presence_keeper")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except BaseException:
                pass
            self._task = None
        try:
            await force_offline(self.c)
        except Exception:
            pass

    async def _loop(self) -> None:
        try:
            await force_offline(self.c)
        except Exception:
            pass
        try:
            while not self._stop.is_set():
                try:
                    if time.monotonic() >= _online_until:
                        await _push(self.c, offline=True)
                except Exception:
                    log.exception("presence keeper tick failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                    return
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return
