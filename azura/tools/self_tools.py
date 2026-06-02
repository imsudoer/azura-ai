"""Self-control tools: presence, mood, journal."""
from __future__ import annotations

from azura.constants import Presence
from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Build self-control tool specs bound to ctx."""

    async def go_afk(args: dict) -> dict:
        minutes = int(args.get("minutes", 10))
        reason = str(args.get("reason", "stepping away"))
        v = await ctx.presence.go_afk(minutes, reason)
        return {"state": v.state.value, "until_ts": v.until_ts}

    async def come_back(_: dict) -> dict:
        v = await ctx.presence.come_back()
        return {"state": v.state.value}

    async def set_presence(args: dict) -> dict:
        s = Presence(args["state"])
        v = await ctx.presence.set(s, reason=args.get("reason"), until_ts=args.get("until_ts"))
        return {"state": v.state.value}

    async def nudge_mood(args: dict) -> dict:
        v = await ctx.mood.nudge(
            valence=float(args.get("valence", 0.0)),
            arousal=float(args.get("arousal", 0.0)),
            stress=float(args.get("stress", 0.0)),
            note=args.get("note"),
        )
        return v.__dict__

    async def journal(args: dict) -> dict:
        await ctx.memory.repos.journal.write(
            str(args["text"]),
            kind=str(args.get("kind", "thought")),
            chat_id=args.get("chat_id") or ctx.chat_id,
            user_id=args.get("user_id"),
        )
        return {"ok": True}

    return [
        make_spec("go_afk",
                  "Step away for a while with a reason (e.g. 'making coffee'). Affects presence.",
                  {"type": "object", "required": ["minutes", "reason"], "properties": {
                      "minutes": {"type": "integer"}, "reason": {"type": "string"}}},
                  go_afk),
        make_spec("come_back",
                  "Return from AFK.",
                  {"type": "object", "properties": {}},
                  come_back),
        make_spec("set_presence",
                  "Force a presence state.",
                  {"type": "object", "required": ["state"], "properties": {
                      "state": {"type": "string", "enum": ["online", "offline", "afk", "busy", "asleep"]},
                      "reason": {"type": "string"}, "until_ts": {"type": "integer"}}},
                  set_presence),
        make_spec("nudge_mood",
                  "Apply an instant mood delta (valence -1..1, arousal/stress 0..1).",
                  {"type": "object", "properties": {
                      "valence": {"type": "number"}, "arousal": {"type": "number"},
                      "stress": {"type": "number"}, "note": {"type": "string"}}},
                  nudge_mood),
        make_spec("journal",
                  "Write a private inner journal line in first person.",
                  {"type": "object", "required": ["text"], "properties": {
                      "text": {"type": "string"}, "kind": {"type": "string"},
                      "chat_id": {"type": "integer"}, "user_id": {"type": "integer"}}},
                  journal),
    ]
