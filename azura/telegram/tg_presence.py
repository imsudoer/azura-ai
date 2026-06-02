"""Push the persona's internal presence into the Telegram account status.

Userbots default to "online" the moment they receive any update from the
server. To convincingly stay offline we need to:
  1. send `account.updateStatus(offline=True)` whenever we want offline;
  2. KEEP RE-SENDING it on a tight interval, otherwise Telegram re-marks
     the account online as soon as the next update is consumed.

This module exposes:
  - `apply_to_telegram(client, state)` for one-shot updates (kept for compat);
  - `PresenceKeeper`, a background loop that re-asserts offline every 25s
     while presence is asleep/offline/afk.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from pyrogram import Client
from pyrogram.raw.functions.account import UpdateStatus

from azura.constants import Presence
from azura.utils.log import get_logger

log = get_logger("tg.presence")


_VISIBLE_ONLINE = {Presence.ONLINE, Presence.BUSY}


def is_offline_state(state: Presence) -> bool:
    return state not in _VISIBLE_ONLINE


async def apply_to_telegram(client: Client, state: Presence) -> None:
    """One-shot push of state to Telegram.

    Sends `account.updateStatus(offline=True)` for ASLEEP/OFFLINE/AFK,
    and `offline=False` for ONLINE/BUSY.
    """
    if client is None:
        return
    offline = is_offline_state(state)
    try:
        await client.invoke(UpdateStatus(offline=offline))
        log.info("tg status -> {} ({})", "offline" if offline else "online", state.value)
    except Exception as e:
        log.warning("UpdateStatus failed: {}", e)


class PresenceKeeper:
    """Background loop that keeps Telegram status in sync with internal state.

    While the persona is in an offline-equivalent state, re-issues
    `updateStatus(offline=True)` every `interval_s` seconds (default 25) so
    that incoming updates can't flip the visible status back to "online".

    When she becomes ONLINE/BUSY, pings `updateStatus(offline=False)` once
    and stops re-asserting (Telegram will keep her online naturally via
    received updates).
    """

    def __init__(
        self,
        client: Client,
        get_state: Callable[[], Awaitable[Presence]],
        *,
        interval_s: float = 25.0,
    ) -> None:
        self.c = client
        self.get_state = get_state
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

    async def _loop(self) -> None:
        last: bool | None = None
        try:
            while not self._stop.is_set():
                try:
                    state = await self.get_state()
                    offline = is_offline_state(state)
                    if offline:
                        try:
                            await self.c.invoke(UpdateStatus(offline=True))
                        except Exception as e:
                            log.warning("keeper UpdateStatus(offline) failed: {}", e)
                    elif last is not False:
                        try:
                            await self.c.invoke(UpdateStatus(offline=False))
                        except Exception as e:
                            log.warning("keeper UpdateStatus(online) failed: {}", e)
                    last = offline
                except Exception:
                    log.exception("presence keeper tick failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                    return
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return
