"""Attention reader: walks the chat priority queue and marks chats as read."""
from __future__ import annotations

import asyncio

from pyrogram import Client

from azura.constants import Presence
from azura.memory.service import MemoryService
from azura.mind.attention import Attention
from azura.mind.mood import MoodView
from azura.mind.presence import PresenceEngine
from azura.utils.log import get_logger
from azura.utils.rng import Rng

log = get_logger("tg.read")


class Reader:
    """Implements the priority schema: private → group → channel → muted private → muted group."""

    def __init__(
        self,
        client: Client,
        *,
        attention: Attention,
        presence: PresenceEngine,
        memory: MemoryService,
        rng: Rng,
    ) -> None:
        self.c = client
        self.attention = attention
        self.presence = presence
        self.memory = memory
        self.rng = rng

    async def cycle(self, *, mood: MoodView, max_chats: int = 6, persona=None) -> int:
        """Reactive attention: pick AT MOST one candidate, weighted by score+mood+laziness.

        Behaviour:
          - hard skip if presence is asleep/offline/afk/busy or in sleep window;
          - draw a single candidate by weighted random over attention scores;
          - laziness chance (proportional to fatigue / low arousal) → skip entirely;
          - opens ONE chat, marks read, returns 1 (or 0).
        """
        cur = await self.presence.current()
        if cur.state in (Presence.ASLEEP, Presence.OFFLINE, Presence.AFK, Presence.BUSY):
            log.info("reader skip: presence={}", cur.state.value)
            return 0
        if persona is not None:
            try:
                from azura.mind.clock import snapshot
                clk = snapshot(persona)
                if clk.is_sleep_window:
                    log.info("reader skip: sleep window (clk)")
                    return 0
            except Exception:
                pass

        laziness = max(0.0, min(0.9, mood.fatigue * 0.6 + (1.0 - mood.arousal) * 0.4))
        if self.rng.chance(laziness * 0.5):
            log.info("reader skip: lazy (fatigue={:.2f} arousal={:.2f})", mood.fatigue, mood.arousal)
            return 0

        queue = await self.attention.queue(mood=mood, limit=max(8, max_chats))
        if not queue:
            return 0

        from azura.mind.attention import Attention as _Att
        top_tier = min(_Att._tier(c) for c in queue)
        same_tier = [c for c in queue if _Att._tier(c) == top_tier]
        weights = [max(0.01, getattr(c, "score", 0.5)) for c in same_tier]
        total = sum(weights)
        r = self.rng.uniform(0.0, total)
        upto = 0.0
        choice = same_tier[0]
        for cand, w in zip(same_tier, weights, strict=True):
            upto += w
            if upto >= r:
                choice = cand
                break
        log.info(
            "reader queue: total={} top_tier={} same_tier={} chose={}",
            len(queue), top_tier, len(same_tier), choice.chat_id,
        )

        unseen = max(0, getattr(choice, "unseen", 0))
        if unseen == 0:
            open_prob = 0.0
        else:
            if top_tier == 0:
                base = 0.55
            elif top_tier == 1:
                base = 0.30
            else:
                base = 0.12
            if unseen >= 5:
                base += 0.25
            elif unseen >= 2:
                base += 0.10
            open_prob = max(0.0, min(0.95, base))

        if not self.rng.chance(open_prob):
            log.info(
                "reader peek-only chat={} tier={} unseen={} open_prob={:.2f} (no online)",
                choice.chat_id, top_tier, unseen, open_prob,
            )
            return 0

        await asyncio.sleep(self.rng.uniform(0.3, 1.6))

        try:
            from azura.telegram.tg_presence import go_online_briefly
            await go_online_briefly(self.c, seconds=15.0)
            att = await self.memory.repos.attention.start(choice.chat_id)
            await self.memory.repos.s.commit()
            await self.c.read_chat_history(choice.chat_id)
            read = await self.memory.repos.messages.mark_seen(choice.chat_id, 10**18)
            await self.memory.repos.attention.finish(att.id, msgs_read=read, decided="read")
            await self.memory.repos.s.commit()
            log.info(
                "reader opened chat={} tier={} unseen={} score={:.2f}",
                choice.chat_id, top_tier, unseen, getattr(choice, "score", 0.0),
            )
            return 1
        except Exception as e:
            err = str(e).lower()
            log.warning("reader failed on chat {}: {}", choice.chat_id, e)
            if "channel_private" in err or "haven't joined" in err or "not a participant" in err:
                try:
                    await self.memory.repos.chats.deactivate(choice.chat_id)
                    await self.memory.repos.s.commit()
                    log.info("reader: deactivated unreachable chat {}", choice.chat_id)
                except Exception:
                    pass
            return 0
