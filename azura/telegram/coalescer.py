"""Per-chat message coalescer.

When several messages arrive into the same chat in rapid succession we don't
want to start an LLM cycle for each one. Instead:

  - The first incoming message starts a debounce timer (`wait_s`).
  - Subsequent messages from the SAME chat extend the timer (up to `max_wait_s`).
  - When the timer fires, a single handler is called with the latest message
    object (the cycle code already has access to the full chat history via DB
    and reads the chat to mark all messages seen).
  - If a new message arrives while the handler is already running AND we are
    still inside the cancellable phase, the handler task is cancelled and a
    new debounce window starts. Once a cycle is past its cancellable phase
    (already started sending), the next batch will wait via the chat lock.

This dramatically reduces races like answering "на что" / "на что" / "на что"
because the operator wrote three messages within 2 seconds.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from azura.utils.log import get_logger

log = get_logger("tg.coalesce")


HandlerFn = Callable[[Any], Awaitable[None]]


@dataclass
class _ChatSlot:
    last_msg: Any | None = None
    pending_ids: list[int] = field(default_factory=list)
    first_ts: float = 0.0
    timer: asyncio.Task | None = None
    runner: asyncio.Task | None = None
    runner_cancellable: bool = True


class Coalescer:
    """Debounce + cancel-and-restart per chat_id."""

    def __init__(
        self,
        handler: HandlerFn,
        *,
        wait_s: float = 4.5,
        max_wait_s: float = 9.0,
    ) -> None:
        self.handler = handler
        self.wait_s = wait_s
        self.max_wait_s = max_wait_s
        self._slots: dict[int, _ChatSlot] = {}
        self._lock = asyncio.Lock()

    async def submit(self, chat_id: int, message: Any) -> None:
        """Register an incoming message; will be handled in a coalesced way."""
        mid = getattr(message, "id", None)
        async with self._lock:
            slot = self._slots.get(chat_id)
            if slot is None:
                slot = _ChatSlot()
                self._slots[chat_id] = slot

            if slot.runner is not None and not slot.runner.done() and slot.runner_cancellable:
                log.info(
                    "coalesce cancel in-flight chat={} new_msg_id={}", chat_id, mid,
                )
                slot.runner.cancel()
                slot.runner = None

            if slot.first_ts == 0.0:
                slot.first_ts = time.monotonic()
            slot.last_msg = message
            if mid is not None and mid not in slot.pending_ids:
                slot.pending_ids.append(mid)

            if slot.timer is not None and not slot.timer.done():
                slot.timer.cancel()

            remaining_budget = self.max_wait_s - (time.monotonic() - slot.first_ts)
            base_wait = self.wait_s if len(slot.pending_ids) > 1 else self.wait_s * 0.6
            wait = max(0.3, min(base_wait, remaining_budget))
            log.info(
                "coalesce queue chat={} mid={} pending={} wait={:.1f}s",
                chat_id, mid, len(slot.pending_ids), wait,
            )
            slot.timer = asyncio.create_task(self._fire_after(chat_id, wait))

    async def mark_runner_committed(self, chat_id: int) -> None:
        """Call this from inside the handler when it crosses the point of no return
        (started sending typing/messages). Further incoming msgs won't cancel us;
        they'll just enqueue a fresh debounce window for the NEXT cycle."""
        async with self._lock:
            slot = self._slots.get(chat_id)
            if slot is not None:
                slot.runner_cancellable = False
                log.debug("coalesce runner committed chat={}", chat_id)

    async def _fire_after(self, chat_id: int, wait: float) -> None:
        try:
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            return
        async with self._lock:
            slot = self._slots.get(chat_id)
            if slot is None or slot.last_msg is None:
                return
            if slot.runner is not None and not slot.runner.done():
                log.debug(
                    "coalesce timer fired but runner active chat={}, deferring to post-run",
                    chat_id,
                )
                return
            msg = slot.last_msg
            count = len(slot.pending_ids)
            slot.last_msg = None
            slot.pending_ids = []
            slot.first_ts = 0.0
            slot.runner_cancellable = True
            slot.timer = None
            slot.runner = asyncio.create_task(self._run(chat_id, msg, count))

    async def _run(self, chat_id: int, msg: Any, count: int) -> None:
        try:
            log.info(
                "coalesce fire chat={} mid={} batch_size={}",
                chat_id, getattr(msg, "id", None), count,
            )
            await self.handler(msg)
        except asyncio.CancelledError:
            log.info("coalesce runner cancelled chat={}", chat_id)
            raise
        except Exception:
            log.exception("coalesce handler failed chat={}", chat_id)
        finally:
            async with self._lock:
                slot = self._slots.get(chat_id)
                if slot and slot.last_msg is not None and slot.pending_ids:
                    pending_msg = slot.last_msg
                    pending_count = len(slot.pending_ids)
                    slot.last_msg = None
                    slot.pending_ids = []
                    slot.first_ts = 0.0
                    slot.runner_cancellable = True
                    if slot.timer and not slot.timer.done():
                        slot.timer.cancel()
                    slot.timer = None
                    log.info(
                        "coalesce post-run: re-fire chat={} pending={}",
                        chat_id, pending_count,
                    )
                    slot.runner = asyncio.create_task(
                        self._run(chat_id, pending_msg, pending_count)
                    )
                else:
                    if slot:
                        slot.runner = None
