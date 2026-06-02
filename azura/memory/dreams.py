"""Nightly dream pass: soften opinions/feelings, keep some globals, reframe episodes."""
from __future__ import annotations

import orjson

from azura.llm.prompts import render
from azura.llm.router import think_json
from azura.memory.service import MemoryService
from azura.mind.mood import MoodEngine
from azura.personality.schema import Persona
from azura.utils.log import get_logger

log = get_logger("memory.dreams")


class Dreams:
    """LLM-driven nightly reflection that gently mutates memory and mood."""

    def __init__(self, persona: Persona, memory: MemoryService, mood: MoodEngine) -> None:
        self.p = persona
        self.m = memory
        self.mood = mood

    async def run(self) -> dict:
        """Execute one dream pass; returns stats."""
        recent_eps = await self.m.repos.episodes.recent(limit=20)
        top_pos = await self.m.repos.opinions.top_n("user", n=10, positive=True)
        top_neg = await self.m.repos.opinions.top_n("user", n=10, positive=False)
        mood = await self.mood.now()
        payload = {
            "mood": mood.__dict__,
            "episodes": [
                {"id": e.id, "title": e.title, "summary": e.summary,
                 "emotion": e.emotion, "intensity": e.intensity}
                for e in recent_eps
            ],
            "positives": [{"id": o.target_id, "score": o.score, "tags": o.tags} for o in top_pos],
            "negatives": [{"id": o.target_id, "score": o.score, "tags": o.tags} for o in top_neg],
        }
        try:
            out = await think_json(
                [
                    {"role": "system", "content": render("dream.j2")},
                    {"role": "user", "content": orjson.dumps(payload).decode()},
                ],
                temperature=0.7,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            log.warning("dream pass failed: {}", e)
            return {"ok": False}

        stats = {"globals": 0, "opinions": 0, "feelings": 0, "reframes": 0}
        for g in (out.get("global_keeps") or []):
            text = str(g.get("content", "")).strip()
            if not text:
                continue
            emb = None
            try:
                emb = await self.m.embeds.get(text)
            except Exception:
                emb = None
            await self.m.global_.add(text, topic=g.get("topic"), embedding=emb)
            stats["globals"] += 1

        for o in (out.get("opinion_softens") or []):
            target = str(o.get("target", "user"))
            delta = int(o.get("delta", 0))
            if delta == 0:
                continue
            if target == "chat":
                await self.m.opinions.bump_chat(int(o["id"]), delta, reason=o.get("reason"))
            else:
                await self.m.opinions.bump_user(int(o["id"]), delta, reason=o.get("reason"))
            stats["opinions"] += 1

        for f in (out.get("feeling_softens") or []):
            delta = float(f.get("delta", 0.0))
            if delta == 0:
                continue
            target = str(f.get("target", "user"))
            if target == "chat":
                await self.m.feelings.bump_chat(int(f["id"]), str(f["emotion"]), delta, reason=f.get("reason"))
            else:
                await self.m.feelings.bump_user(int(f["id"]), str(f["emotion"]), delta, reason=f.get("reason"))
            stats["feelings"] += 1

        for ref in (out.get("episode_reframes") or []):
            try:
                ep = await self.m.repos.s.get(__import__("azura.db.models", fromlist=["Episode"]).Episode, int(ref["id"]))
                if ep:
                    ep.summary = str(ref.get("new_summary", ep.summary))[:1024]
                    stats["reframes"] += 1
            except Exception:
                continue

        dj = (out.get("dream_journal") or "").strip()
        if dj:
            await self.m.repos.journal.write(dj, kind="dream")

        await self.mood.sleep_reset()
        await self.m.repos.s.commit()
        return stats
