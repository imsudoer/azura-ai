"""Sticker management: pick by mood, learn new ones, tag them."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Sticker library tools."""

    async def pick_sticker(args: dict) -> dict:
        v = float(args.get("valence", 0.0))
        a = float(args.get("arousal", 0.5))
        items = await ctx.memory.repos.stickers.pick_by_mood(valence=v, arousal=a, limit=5)
        return {"candidates": [
            {"id": s.id, "file_id": s.file_id, "tags": s.tags, "fits": s.fits_persona} for s in items
        ]}

    async def learn_sticker(args: dict) -> dict:
        s = await ctx.memory.repos.stickers.upsert(
            file_id=str(args["file_id"]),
            file_unique_id=args.get("file_unique_id"),
            set_name=args.get("set_name"),
            emoji=args.get("emoji"),
        )
        await ctx.memory.repos.stickers.tag(
            s.id,
            tags=args.get("tags") or [],
            mood_valence=args.get("mood_valence"),
            mood_arousal=args.get("mood_arousal"),
            description=args.get("description"),
            fits_persona=args.get("fits_persona"),
        )
        return {"id": s.id}

    return [
        make_spec("pick_sticker",
                  "Pick a sticker from your collection that fits a given mood.",
                  {"type": "object", "properties": {
                      "valence": {"type": "number"}, "arousal": {"type": "number"}}},
                  pick_sticker),
        make_spec("learn_sticker",
                  "Save a sticker you just saw with tags, mood and persona fit.",
                  {"type": "object", "required": ["file_id"], "properties": {
                      "file_id": {"type": "string"},
                      "file_unique_id": {"type": "string"},
                      "set_name": {"type": "string"},
                      "emoji": {"type": "string"},
                      "tags": {"type": "array", "items": {"type": "string"}},
                      "mood_valence": {"type": "number"},
                      "mood_arousal": {"type": "number"},
                      "description": {"type": "string"},
                      "fits_persona": {"type": "number"}}},
                  learn_sticker),
    ]
