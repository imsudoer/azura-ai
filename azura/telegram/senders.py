"""Humanized outbound message sender: delays, typing, typos, split, backpressure."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from pyrogram import Client
from pyrogram.enums import ChatAction

from azura.humanize.anti_detect import sanitize
from azura.humanize.backpressure import Backpressure
from azura.humanize.delays import reply_delay, split_burst_delays
from azura.humanize.splitter import split_reply
from azura.humanize.style_diversity import StyleDiversity
from azura.humanize.typing import type_with_ticks
from azura.humanize.typos import correction_messages, inject_typos
from azura.memory.service import MemoryService
from azura.mind.clock import ClockSnapshot
from azura.mind.mood import MoodView
from azura.personality.schema import Persona
from azura.utils.log import get_logger
from azura.utils.rng import Rng
from azura.utils.timez import ts

log = get_logger("tg.send")


@dataclass
class SendResult:
    """Outcome of one humanized send call."""
    sent: int
    skipped: int
    delays: dict[str, float]


class Sender:
    """Send 1..N messages with human-shaped timing and typing actions."""

    def __init__(
        self,
        client: Client,
        *,
        persona: Persona,
        memory: MemoryService,
        rng: Rng,
        backpressure: Backpressure,
        style: StyleDiversity,
    ) -> None:
        self.c = client
        self.p = persona
        self.m = memory
        self.rng = rng
        self.bp = backpressure
        self.style = style

    async def send(
        self,
        chat_id: int,
        messages: list[str],
        *,
        mood: MoodView,
        clock: ClockSnapshot,
        in_private: bool,
        urgency: float = 0.2,
        reply_to: int | None = None,
        do_split: bool = True,
    ) -> SendResult:
        """Run the whole humanize pipeline for one outgoing burst."""
        msgs = [m for m in (messages or []) if isinstance(m, str) and m.strip()]
        if not msgs:
            return SendResult(0, 0, {})
        joined = "\n\n".join(msgs)
        clean, notes = sanitize(joined, persona=self.p)
        if not clean:
            log.info("skipped (sanitize) chat={}: {}", chat_id, notes)
            return SendResult(0, len(msgs), {})

        if do_split:
            parts = split_reply(clean, persona=self.p, rng=self.rng)
        else:
            parts = [clean]
        if not parts:
            return SendResult(0, 1, {})

        if self.style.too_similar(clean, chat_id=chat_id):
            log.info("style-diversity blocked chat={} (overlap)", chat_id)
            return SendResult(0, len(parts), {})

        total_len = sum(len(p) for p in parts)
        plan = reply_delay(
            persona=self.p, mood=mood, clock=clock, rng=self.rng,
            text_len=total_len, urgency=urgency, in_private=in_private,
        )

        await self.bp.gate(chat_id)
        from azura.telegram.tg_presence import go_online_briefly
        await go_online_briefly(self.c, seconds=max(45.0, plan.pre_read_s + plan.pre_type_s + plan.type_burst_s + 30.0))

        log.info(
            "reply gate chat={} pre_read={:.1f}s pre_type={:.1f}s burst={:.1f}s parts={} chars={}",
            chat_id, plan.pre_read_s, plan.pre_type_s, plan.type_burst_s, len(parts), total_len,
        )
        if plan.pre_read_s > 0:
            await asyncio.sleep(plan.pre_read_s)
        log.debug("reply gate chat={} -> read_chat_history (1/2)", chat_id)
        try:
            await self.c.read_chat_history(chat_id)
        except Exception as e:
            log.warning("read_chat_history failed chat={} err={}", chat_id, e)
        think_s = self.rng.uniform(0.6, 2.2)
        log.debug("reply gate chat={} think pause {:.1f}s", chat_id, think_s)
        await asyncio.sleep(think_s)
        try:
            await self.c.read_chat_history(chat_id)
        except Exception:
            pass

        between = split_burst_delays(self.rng, len(parts))
        sent = 0
        all_typos: list[tuple[str, str]] = []
        for i, part in enumerate(parts):
            await asyncio.sleep(plan.pre_type_s if i == 0 else self.rng.uniform(0.4, 1.4))
            text_to_type, typos = inject_typos(part, rate=self.p.speech.typos_rate, rng=self.rng)
            all_typos.extend(typos)
            type_s = max(0.6, plan.type_burst_s * (len(part) / max(1, total_len)))
            await type_with_ticks(
                chat_id=chat_id, total_seconds=type_s,
                keepalive=lambda cid: self.c.send_chat_action(cid, ChatAction.TYPING),
            )
            await self.bp.gate(chat_id)
            kwargs: dict[str, Any] = {"chat_id": chat_id, "text": text_to_type}
            if i == 0 and reply_to is not None:
                kwargs["reply_to_message_id"] = reply_to
            await self.c.send_message(**kwargs)
            self.style.add(text_to_type, chat_id=chat_id)
            sent += 1
            if i < len(between):
                await asyncio.sleep(between[i])

        corrections = correction_messages(
            all_typos, rng=self.rng, chance=self.p.speech.self_correction_chance,
        )
        for c in corrections:
            await asyncio.sleep(self.rng.uniform(1.2, 3.0))
            await self.bp.gate(chat_id)
            await self.c.send_message(chat_id=chat_id, text=c)
            sent += 1

        await asyncio.sleep(plan.after_send_s)
        try:
            await self.c.read_chat_history(chat_id)
        except Exception:
            pass
        try:
            from azura.telegram.tg_presence import go_online_briefly
            await go_online_briefly(self.c, seconds=20.0)
        except Exception:
            pass
        return SendResult(
            sent=sent, skipped=0,
            delays={
                "pre_read": plan.pre_read_s, "pre_type": plan.pre_type_s,
                "type_burst": plan.type_burst_s, "after": plan.after_send_s,
                "since_ts": ts(),
            },
        )
