"""Operator tools exposed only via the operator channel."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Operator-only utilities (status, force sleep/wake, dump)."""

    async def status(_: dict) -> dict:
        mood = await ctx.mood.now()
        pres = await ctx.presence.current()
        return {
            "mood": mood.__dict__,
            "presence": {"state": pres.state.value, "reason": pres.reason, "until_ts": pres.until_ts},
        }

    async def force_sleep(_: dict) -> dict:
        from azura.constants import Presence
        v = await ctx.presence.set(Presence.ASLEEP, reason="forced by operator")
        return {"state": v.state.value}

    async def force_wake(_: dict) -> dict:
        from azura.constants import Presence
        v = await ctx.presence.set(Presence.ONLINE, reason="forced wake")
        return {"state": v.state.value}

    async def journal_tail(args: dict) -> dict:
        items = await ctx.memory.repos.journal.recent(limit=int(args.get("limit", 30)))
        return {"items": [{"ts": it.ts, "kind": it.kind, "text": it.text} for it in items]}

    return [
        make_spec("op_status", "Return mood + presence snapshot for operator.",
                  {"type": "object", "properties": {}}, status),
        make_spec("op_force_sleep", "Force persona to sleep.",
                  {"type": "object", "properties": {}}, force_sleep),
        make_spec("op_force_wake", "Force persona to wake up.",
                  {"type": "object", "properties": {}}, force_wake),
        make_spec("op_journal", "Read recent journal entries.",
                  {"type": "object", "properties": {"limit": {"type": "integer"}}}, journal_tail),
    ]
