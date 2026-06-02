"""Tools for recall and updates to memory/opinions/feelings/relationships."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Build memory-related tool specs bound to ctx."""

    async def recall_user(args: dict) -> dict:
        uid = int(args["user_id"])
        q = args.get("query") or None
        return await ctx.memory.recall_about_user(uid, query=q)

    async def recall_chat(args: dict) -> dict:
        cid = int(args.get("chat_id") or ctx.chat_id or 0)
        return await ctx.memory.recall_chat(cid)

    async def search_memory(args: dict) -> dict:
        q = str(args.get("query", ""))
        long_hits = await ctx.memory.long.search(q, limit=int(args.get("limit", 6)))
        ep_hits = await ctx.memory.episodic.search(q, limit=int(args.get("limit", 6)))
        return {"long": long_hits, "episodes": ep_hits}

    async def remember_fact(args: dict) -> dict:
        emb = None
        text = str(
            args.get("content") or args.get("text") or args.get("fact")
            or args.get("summary") or args.get("note") or ""
        ).strip()
        if not text:
            return {"error": "empty content"}
        try:
            emb = await ctx.memory.embeds.get(text)
        except Exception:
            emb = None
        mid = await ctx.memory.long.add_fact(
            text,
            chat_id=args.get("chat_id"),
            user_id=args.get("user_id"),
            topic=args.get("topic"),
            confidence=float(args.get("confidence", 0.8)),
            importance=float(args.get("importance", 0.6)),
            embedding=emb,
        )
        return {"id": mid}

    async def remember_episode(args: dict) -> dict:
        text = str(
            args.get("summary") or args.get("content") or args.get("text") or ""
        ).strip()
        if not text:
            return {"error": "empty summary"}
        title = str(args.get("title") or text[:60]).strip()
        emb = None
        try:
            emb = await ctx.memory.embeds.get(text)
        except Exception:
            emb = None
        eid = await ctx.memory.episodic.remember(
            title=title,
            summary=text,
            chat_id=args.get("chat_id") or ctx.chat_id,
            user_id=args.get("user_id"),
            emotion=args.get("emotion"),
            intensity=float(args.get("intensity", 0.5)),
            embedding=emb,
        )
        return {"id": eid}

    async def update_opinion(args: dict) -> dict:
        target = str(args["target"])
        delta = int(args["delta"])
        reason = args.get("reason")
        tags = args.get("tags") or None
        if target == "user":
            score = await ctx.memory.opinions.bump_user(int(args["id"]), delta, tags=tags, reason=reason)
        elif target == "chat":
            score = await ctx.memory.opinions.bump_chat(int(args["id"]), delta, tags=tags, reason=reason)
        else:
            score = await ctx.memory.opinions.bump_topic(str(args["id"]), delta, reason=reason)
        return {"score": score}

    async def update_feeling(args: dict) -> dict:
        target = str(args.get("target", "user"))
        if target == "chat":
            v = await ctx.memory.feelings.bump_chat(
                int(args["id"]), str(args["emotion"]), float(args.get("delta", 0.1)), reason=args.get("reason")
            )
        else:
            v = await ctx.memory.feelings.bump_user(
                int(args["id"]), str(args["emotion"]), float(args.get("delta", 0.1)), reason=args.get("reason")
            )
        return {"intensity": v}

    async def note_relationship(args: dict) -> dict:
        await ctx.memory.relationships.note(
            int(args["a_id"]), int(args["b_id"]),
            kind=str(args.get("kind", "neutral")),
            chat_id=args.get("chat_id"),
            strength=float(args.get("strength", 0.5)),
            notes=args.get("notes"),
        )
        return {"ok": True}

    return [
        make_spec("recall_user",
                  "Bundle what you remember about a user (opinion, feelings, proximity, facts, episodes).",
                  {"type": "object", "required": ["user_id"], "properties": {
                      "user_id": {"type": "integer"},
                      "query": {"type": "string"},
                  }},
                  recall_user),
        make_spec("recall_chat",
                  "Bundle the chat context: short-term notes, long-term facts, chat opinion, feelings.",
                  {"type": "object", "properties": {"chat_id": {"type": "integer"}}},
                  recall_chat),
        make_spec("search_memory",
                  "Search long-term and episodic memory by free text.",
                  {"type": "object", "required": ["query"], "properties": {
                      "query": {"type": "string"}, "limit": {"type": "integer"}}},
                  search_memory),
        make_spec("remember_fact",
                  "Save a stable fact you want to keep about a person/chat/topic.",
                  {"type": "object", "required": ["content"], "properties": {
                      "content": {"type": "string"}, "chat_id": {"type": "integer"},
                      "user_id": {"type": "integer"}, "topic": {"type": "string"},
                      "confidence": {"type": "number"}, "importance": {"type": "number"}}},
                  remember_fact),
        make_spec("remember_episode",
                  "Save an event with a title, summary, emotion and intensity.",
                  {"type": "object", "required": ["title", "summary"], "properties": {
                      "title": {"type": "string"}, "summary": {"type": "string"},
                      "user_id": {"type": "integer"}, "chat_id": {"type": "integer"},
                      "emotion": {"type": "string"}, "intensity": {"type": "number"}}},
                  remember_episode),
        make_spec("update_opinion",
                  "Adjust opinion score (-100..+100) about a user / chat / topic.",
                  {"type": "object", "required": ["target", "id", "delta"], "properties": {
                      "target": {"type": "string", "enum": ["user", "chat", "topic"]},
                      "id": {"type": ["integer", "string"]},
                      "delta": {"type": "integer"},
                      "reason": {"type": "string"},
                      "tags": {"type": "array", "items": {"type": "string"}}}},
                  update_opinion),
        make_spec("update_feeling",
                  "Push intensity of an emotion (0..1) toward a user or chat.",
                  {"type": "object", "required": ["id", "emotion"], "properties": {
                      "target": {"type": "string", "enum": ["user", "chat"]},
                      "id": {"type": "integer"}, "emotion": {"type": "string"},
                      "delta": {"type": "number"}, "reason": {"type": "string"}}},
                  update_feeling),
        make_spec("note_relationship",
                  "Note an observed relation between two peers (friends, dating, rivals, etc).",
                  {"type": "object", "required": ["a_id", "b_id", "kind"], "properties": {
                      "a_id": {"type": "integer"}, "b_id": {"type": "integer"},
                      "kind": {"type": "string"}, "chat_id": {"type": "integer"},
                      "strength": {"type": "number"}, "notes": {"type": "string"}}},
                  note_relationship),
    ]
