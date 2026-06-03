"""Telegram-visible online status: offline-by-default, brief online windows.

Every status flip logs WHO requested it (`reason`) plus the duration of the
online window. If you see `tg status -> online (reason=??)` and you didn't
expect it, search the codebase for that reason string to find the caller.
"""
from __future__ import annotations

import asyncio
import time
import traceback

from pyrogram import Client
from pyrogram.raw.functions.account import UpdateStatus

from azura.utils.log import get_logger

log = get_logger("tg.presence")


_state_lock = asyncio.Lock()
_online_until: float = 0.0
_last_pushed: bool | None = None
_last_reason: str = ""


async def _push(client: Client, offline: bool, *, reason: str = "") -> None:
    global _last_pushed, _last_reason
    try:
        await client.invoke(UpdateStatus(offline=offline))
        if _last_pushed != offline:
            log.info(
                "tg status -> {} (reason={!r}, prev_reason={!r})",
                "offline" if offline else "online",
                reason, _last_reason,
            )
        _last_pushed = offline
        if reason:
            _last_reason = reason
    except Exception as e:
        log.warning("UpdateStatus(offline={}) failed: {}", offline, e)


async def go_online_briefly(
    client: Client, *, seconds: float = 45.0, reason: str = "unknown",
) -> None:
    """Mark Telegram online; auto-offline scheduled `seconds` later.

    Always pass `reason` so we can trace why she lit up. Examples:
      - "sender.reply"     — answering a message
      - "reader.open"      — opened a chat from peek
      - "react"            — placing a reaction
      - "op.direct"        — operator direct-sender
      - "self_initiate"    — she decided to write first
    """
    global _online_until
    if client is None:
        return
    async with _state_lock:
        was_offline = _last_pushed is not False
        _online_until = max(_online_until, time.monotonic() + seconds)
        await _push(client, offline=False, reason=reason)
    log.info(
        "go_online_briefly reason={!r} seconds={:.0f} was_offline={}",
        reason, seconds, was_offline,
    )
    log.debug(
        "go_online_briefly caller stack:\n{}",
        "".join(traceback.format_stack(limit=8)[:-1]).rstrip(),
    )


async def force_offline(client: Client, *, reason: str = "explicit") -> None:
    """Force offline immediately and clear the online window."""
    global _online_until
    if client is None:
        return
    async with _state_lock:
        _online_until = 0.0
        await _push(client, offline=True, reason=reason)


class PresenceKeeper:
    """Background loop that re-asserts offline outside the explicit online window."""

    def __init__(self, client: Client, *, interval_s: float = 20.0) -> None:
        self.c = client
        self.interval = interval_s
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="presence_keeper")
            log.info("PresenceKeeper started interval={}s", self.interval)

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
            await force_offline(self.c, reason="shutdown")
        except Exception:
            pass

    async def _loop(self) -> None:
        try:
            await force_offline(self.c, reason="keeper-boot")
        except Exception:
            pass
        try:
            while not self._stop.is_set():
                try:
                    if time.monotonic() >= _online_until:
                        await _push(self.c, offline=True, reason="keeper-tick")
                except Exception:
                    log.exception("presence keeper tick failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                    return
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return
