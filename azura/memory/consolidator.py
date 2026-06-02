"""Consolidate short-term notes into long-term facts, opinions, feelings, episodes."""
from __future__ import annotations

import orjson

from azura.constants import MemoryKind
from azura.llm.prompts import render
from azura.llm.router import think_json
from azura.memory.service import MemoryService
from azura.personality.schema import Persona
from azura.utils.log import get_logger

log = get_logger("memory.consolidator")


class Consolidator:
    """Walk every chat with recent short-term memory and persist what matters."""

    def __init__(self, persona: Persona, memory: MemoryService) -> None:
        self.p = persona
        self.m = memory

    async def consolidate_chat(self, chat_id: int, *, max_notes: int = 60) -> dict:
        """Consolidate the recent short-term notes for one chat into long/episodic/opinions/feelings."""
        notes = await self.m.short.recent(chat_id, limit=max_notes)
        if not notes:
            return {"facts": 0, "episodes": 0, "opinion_updates": 0, "feeling_updates": 0}
        payload = {"chat_id": chat_id, "notes": notes}
        try:
            out = await think_json(
                [
                    {"role": "system", "content": render("consolidate.j2")},
                    {"role": "user", "content": orjson.dumps(payload).decode()},
                ],
                temperature=0.4,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            log.warning("consolidate failed chat={}: {}", chat_id, e)
            return {"facts": 0, "episodes": 0, "opinion_updates": 0, "feeling_updates": 0}

        stats = {"facts": 0, "episodes": 0, "opinion_updates": 0, "feeling_updates": 0}
        for f in (out.get("facts") or []):
            text = str(f.get("content", "")).strip()
            if not text:
                continue
            emb = None
            try:
                emb = await self.m.embeds.get(text)
            except Exception:
                emb = None
            await self.m.long.add_fact(
                text,
                chat_id=chat_id,
                user_id=f.get("user_id"),
                topic=f.get("topic"),
                confidence=float(f.get("confidence", 0.8)),
                importance=float(f.get("importance", 0.6)),
                embedding=emb,
            )
            stats["facts"] += 1

        for ep in (out.get("episodes") or []):
            title = str(ep.get("title", "")).strip()
            summary = str(ep.get("summary", "")).strip()
            if not title or not summary:
                continue
            emb = None
            try:
                emb = await self.m.embeds.get(summary)
            except Exception:
                emb = None
            await self.m.episodic.remember(
                title=title, summary=summary, chat_id=chat_id,
                user_id=ep.get("user_id"), emotion=ep.get("emotion"),
                intensity=float(ep.get("intensity", 0.5)), embedding=emb,
            )
            stats["episodes"] += 1

        for op in (out.get("opinion_updates") or []):
            target = str(op.get("target", "user"))
            delta = int(op.get("delta", 0))
            if delta == 0:
                continue
            if target == "user":
                await self.m.opinions.bump_user(int(op["id"]), delta, reason=op.get("reason"))
            elif target == "chat":
                await self.m.opinions.bump_chat(int(op["id"]), delta, reason=op.get("reason"))
            else:
                await self.m.opinions.bump_topic(str(op["id"]), delta, reason=op.get("reason"))
            stats["opinion_updates"] += 1

        for ff in (out.get("feeling_updates") or []):
            target = str(ff.get("target", "user"))
            delta = float(ff.get("delta", 0.0))
            if delta == 0:
                continue
            if target == "chat":
                await self.m.feelings.bump_chat(int(ff["id"]), str(ff["emotion"]), delta, reason=ff.get("reason"))
            else:
                await self.m.feelings.bump_user(int(ff["id"]), str(ff["emotion"]), delta, reason=ff.get("reason"))
            stats["feeling_updates"] += 1

        await self.m.repos.s.commit()
        await self.m.repos.journal.write(
            f"consolidated chat {chat_id}: {stats}", kind="consolidate", chat_id=chat_id,
        )
        return stats

    async def consolidate_all_active(self) -> dict:
        """Iterate over chats that have any recent short-term memory."""
        recent = await self.m.repos.memory.recent(MemoryKind.SHORT.value, limit=2000)
        chat_ids = sorted({m.chat_id for m in recent if m.chat_id})
        total = {"chats": 0, "facts": 0, "episodes": 0, "opinion_updates": 0, "feeling_updates": 0}
        for cid in chat_ids:
            st = await self.consolidate_chat(cid)
            total["chats"] += 1
            for k in ("facts", "episodes", "opinion_updates", "feeling_updates"):
                total[k] += st.get(k, 0)
        return total
