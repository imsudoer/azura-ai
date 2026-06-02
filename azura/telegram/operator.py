"""Operator-only command channel. Filters on TG id + secret prefix."""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Callable, Awaitable

from pyrogram import Client
from pyrogram.types import Message

from azura.config import Settings
from azura.tools.context import ToolContext
from azura.tools.operator_tools import build as op_build
from azura.utils.log import get_logger

log = get_logger("tg.operator")


@dataclass
class OpResult:
    """Reply payload to send back to the operator."""
    text: str


async def handle(client: Client, msg: Message, *, ctx: ToolContext, settings: Settings) -> bool:
    """Dispatch one operator command. Returns True if it was handled."""
    if not msg.from_user or msg.from_user.id != settings.operator_id:
        return False
    if not msg.chat or msg.chat.type.value != "private":
        return False
    body = (msg.text or msg.caption or "").strip()
    if not body.startswith(settings.operator_secret):
        return False
    args = body[len(settings.operator_secret):].strip()
    if not args:
        await client.send_message(msg.chat.id, "ok, listening. try: status, sleep, wake, journal [N], pause, resume")
        return True

    try:
        parts = shlex.split(args)
    except ValueError:
        parts = args.split()
    cmd, *rest = parts
    cmd = cmd.lower()
    by_name = {t.name: t for t in op_build(ctx)}

    if cmd == "status":
        r = await by_name["op_status"].fn({})
        await client.send_message(msg.chat.id, _fmt_status(r))
        return True
    if cmd == "sleep":
        await by_name["op_force_sleep"].fn({})
        await client.send_message(msg.chat.id, "→ asleep")
        return True
    if cmd == "wake":
        await by_name["op_force_wake"].fn({})
        await client.send_message(msg.chat.id, "→ online")
        return True
    if cmd == "journal":
        limit = int(rest[0]) if rest and rest[0].isdigit() else 10
        r = await by_name["op_journal"].fn({"limit": limit})
        await client.send_message(msg.chat.id, _fmt_journal(r))
        return True
    if cmd in ("pause", "resume"):
        from azura.constants import Presence
        target = Presence.OFFLINE if cmd == "pause" else Presence.ONLINE
        await ctx.presence.set(target, reason=f"operator {cmd}")
        await client.send_message(msg.chat.id, f"→ {target.value}")
        return True

    await client.send_message(msg.chat.id, f"unknown op cmd: {cmd}")
    return True


def _fmt_status(r: dict) -> str:
    m = r.get("mood", {})
    p = r.get("presence", {})
    return (
        f"presence: {p.get('state')} ({p.get('reason')})\n"
        f"mood: v={m.get('valence'):.2f} a={m.get('arousal'):.2f} "
        f"en={m.get('energy'):.2f} st={m.get('stress'):.2f} "
        f"fa={m.get('fatigue'):.2f}"
    )


def _fmt_journal(r: dict) -> str:
    items = r.get("items") or []
    if not items:
        return "(empty journal)"
    return "\n".join(f"[{it['kind']}] {it['text']}" for it in items)
