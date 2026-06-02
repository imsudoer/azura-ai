"""GIF tools: pick by tags, learn new ones."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Gif library tools."""

    async def pick_gif(args: dict) -> dict:
        tags = list(args.get("tags") or [])
        items = await ctx.memory.repos.gifs.pick_by_tags(tags, limit=5)
        return {"candidates": [
            {"id": g.id, "file_id": g.file_id, "tags": g.tags} for g in items
        ]}

    async def learn_gif(args: dict) -> dict:
        g = await ctx.memory.repos.gifs.upsert(
            file_id=str(args["file_id"]),
            file_unique_id=args.get("file_unique_id"),
            tags=args.get("tags") or [],
            description=args.get("description"),
            fits_persona=args.get("fits_persona"),
        )
        return {"id": g.id}

    return [
        make_spec("pick_gif",
                  "Pick a GIF from your collection by tags.",
                  {"type": "object", "properties": {
                      "tags": {"type": "array", "items": {"type": "string"}}}},
                  pick_gif),
        make_spec("learn_gif",
                  "Save a GIF you just saw with tags.",
                  {"type": "object", "required": ["file_id"], "properties": {
                      "file_id": {"type": "string"},
                      "file_unique_id": {"type": "string"},
                      "tags": {"type": "array", "items": {"type": "string"}},
                      "description": {"type": "string"},
                      "fits_persona": {"type": "number"}}},
                  learn_gif),
    ]
