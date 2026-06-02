"""Web tools: search & fetch, gated behind AFK to keep human presence illusion."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Web tools that visibly take time."""

    async def web_search(args: dict) -> dict:
        if ctx.web_searcher is None:
            return {"error": "web_searcher not bound"}
        await ctx.presence.go_afk(int(args.get("afk_minutes", 1)), reason="looking smth up")
        try:
            res = await ctx.web_searcher(str(args["query"]))
            return {"results": res[: int(args.get("limit", 5))]}
        finally:
            await ctx.presence.come_back()

    async def web_fetch(args: dict) -> dict:
        if ctx.web_fetcher is None:
            return {"error": "web_fetcher not bound"}
        await ctx.presence.go_afk(int(args.get("afk_minutes", 1)), reason="reading a link")
        try:
            body = await ctx.web_fetcher(str(args["url"]))
            return {"text": body[: int(args.get("max_chars", 4000))]}
        finally:
            await ctx.presence.come_back()

    return [
        make_spec("web_search",
                  "Search the web. You will appear AFK while you do.",
                  {"type": "object", "required": ["query"], "properties": {
                      "query": {"type": "string"}, "limit": {"type": "integer"},
                      "afk_minutes": {"type": "integer"}}},
                  web_search),
        make_spec("web_fetch",
                  "Open a URL and read its text. You will appear AFK while reading.",
                  {"type": "object", "required": ["url"], "properties": {
                      "url": {"type": "string"}, "max_chars": {"type": "integer"},
                      "afk_minutes": {"type": "integer"}}},
                  web_fetch),
    ]
