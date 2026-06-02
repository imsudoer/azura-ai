"""When a sticker or GIF is seen, persist it and queue an LLM tagging pass."""
from __future__ import annotations

import asyncio

import orjson
from pyrogram.types import Message

from azura.llm.router import think_json
from azura.memory.service import MemoryService
from azura.personality.schema import Persona
from azura.utils.log import get_logger

log = get_logger("tg.collector")

_TAG_SYS = (
    "You receive a description of a single sticker or GIF and a persona summary. "
    "Return STRICT JSON: {tags:[5..10 short strings], description:string, "
    "mood_valence:-1..1, mood_arousal:0..1, fits_persona:0..1}. JSON only."
)


def _persona_brief(p: Persona) -> dict:
    return {
        "name": p.identity.name,
        "humor": p.derived.get("humor_style"),
        "register": p.speech.speech_register,
        "interests": p.interests[:10],
        "avoid": p.speech.avoid_words[:10],
        "playfulness": p.traits.get("playfulness"),
        "sarcasm": p.traits.get("sarcasm"),
    }


class StickersCollector:
    """Persist incoming sticker/gif file_ids and (async) tag them via the think model."""

    def __init__(self, persona: Persona, memory: MemoryService) -> None:
        self.p = persona
        self.m = memory

    async def on_sticker(self, message: Message) -> None:
        st = message.sticker
        if not st:
            return
        row = await self.m.repos.stickers.upsert(
            file_id=st.file_id,
            file_unique_id=getattr(st, "file_unique_id", None),
            set_name=getattr(st, "set_name", None),
            emoji=getattr(st, "emoji", None),
        )
        asyncio.create_task(self._tag_sticker(row.id, st))

    async def on_animation(self, message: Message) -> None:
        a = message.animation
        if not a:
            return
        row = await self.m.repos.gifs.upsert(
            file_id=a.file_id,
            file_unique_id=getattr(a, "file_unique_id", None),
            description=getattr(a, "file_name", None),
        )
        asyncio.create_task(self._tag_gif(row.id, a))

    async def _tag_sticker(self, sticker_id: int, st) -> None:
        try:
            payload = {
                "kind": "sticker",
                "emoji": getattr(st, "emoji", None),
                "set_name": getattr(st, "set_name", None),
                "persona": _persona_brief(self.p),
            }
            out = await think_json(
                [
                    {"role": "system", "content": _TAG_SYS},
                    {"role": "user", "content": orjson.dumps(payload).decode()},
                ],
                temperature=0.4,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            await self.m.repos.stickers.tag(
                sticker_id,
                tags=out.get("tags") or [],
                mood_valence=out.get("mood_valence"),
                mood_arousal=out.get("mood_arousal"),
                description=out.get("description"),
                fits_persona=out.get("fits_persona"),
            )
            await self.m.repos.s.commit()
        except Exception as e:
            log.warning("sticker tag failed id={}: {}", sticker_id, e)

    async def _tag_gif(self, gif_id: int, a) -> None:
        try:
            payload = {
                "kind": "gif",
                "file_name": getattr(a, "file_name", None),
                "persona": _persona_brief(self.p),
            }
            out = await think_json(
                [
                    {"role": "system", "content": _TAG_SYS},
                    {"role": "user", "content": orjson.dumps(payload).decode()},
                ],
                temperature=0.4,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            await self.m.repos.gifs.upsert(
                file_id=a.file_id,
                tags=out.get("tags") or [],
                description=out.get("description"),
                fits_persona=out.get("fits_persona"),
            )
            await self.m.repos.s.commit()
        except Exception as e:
            log.warning("gif tag failed id={}: {}", gif_id, e)
