"""Operator channel: explicit slash-style commands + LLM dual-mode NL commands.

The operator is the only Telegram user allowed to issue control commands; identity
is verified via TG user id + private chat. The legacy prefixed `<SECRET> cmd ...`
slash interface remains for unambiguous control. Any other message from the
operator goes through an LLM intent classifier:

  - If "command" — translates into one or more tool calls and executes them.
  - If "chat"    — returns False so the regular Dispatcher cycle answers as persona.
"""
from __future__ import annotations

import shlex
from typing import Any

import orjson
from pyrogram import Client
from pyrogram.types import Message

from azura.config import Settings
from azura.llm.prompts import render
from azura.llm.router import think_json
from azura.tools.builder import build_registry
from azura.tools.context import ToolContext
from azura.tools.operator_tools import build as op_build
from azura.utils.log import get_logger

log = get_logger("tg.operator")


def is_operator_chat(msg: Message, settings: Settings) -> bool:
    """True iff the message is a private DM from the configured operator."""
    if not msg.from_user or msg.from_user.id != settings.operator_id:
        return False
    if not msg.chat or getattr(msg.chat.type, "value", "") != "private":
        return False
    return True


async def handle(
    client: Client, msg: Message, *, ctx: ToolContext, settings: Settings
) -> bool:
    """Dispatch operator messages. Returns True if handled (don't forward to persona)."""
    if not is_operator_chat(msg, settings):
        return False
    body = (msg.text or msg.caption or "").strip()
    if not body:
        return False

    if body.startswith(settings.operator_secret):
        return await _handle_slash(client, msg, body[len(settings.operator_secret):].strip(),
                                   ctx=ctx, settings=settings)

    return await _handle_nl(client, msg, body, ctx=ctx, settings=settings)


async def _handle_slash(
    client: Client, msg: Message, args: str, *, ctx: ToolContext, settings: Settings
) -> bool:
    """Explicit `<SECRET> cmd ...` interface for unambiguous commands."""
    if not args:
        await client.send_message(
            msg.chat.id,
            "listening. try: status, sleep, wake, journal [N], pause, resume, "
            "rebootstrap, regen_portrait, set_name X, set_username X, ban N, unban N",
        )
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
        await by_name["op_force_sleep"].fn({}); await client.send_message(msg.chat.id, "→ asleep")
        return True
    if cmd == "wake":
        await by_name["op_force_wake"].fn({}); await client.send_message(msg.chat.id, "→ online")
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
    if cmd in ("rebootstrap", "bootstrap"):
        from azura.telegram.bootstrap import run as run_bootstrap
        res = await run_bootstrap(client, ctx.memory.repos, ctx.persona, force=True)
        await client.send_message(msg.chat.id, "bootstrap:\n" + orjson.dumps(res, option=orjson.OPT_INDENT_2).decode()[:3500])
        return True
    if cmd in ("regen_portrait", "regen_avatar", "new_photo"):
        from azura.telegram.bootstrap import generate_and_set_photo
        res = await generate_and_set_photo(client, ctx.persona)
        await client.send_message(msg.chat.id, "portrait: " + orjson.dumps(res).decode()[:1500])
        return True
    if cmd in ("set_name",) and rest:
        await client.update_profile(first_name=" ".join(rest))
        await client.send_message(msg.chat.id, "→ name updated")
        return True
    if cmd in ("set_username",) and rest:
        await client.set_username(rest[0])
        await client.send_message(msg.chat.id, f"→ @{rest[0]}")
        return True
    if cmd in ("ban", "block") and rest:
        await client.block_user(_parse_user(rest[0]))
        await client.send_message(msg.chat.id, "→ blocked")
        return True
    if cmd in ("unban", "unblock") and rest:
        await client.unblock_user(_parse_user(rest[0]))
        await client.send_message(msg.chat.id, "→ unblocked")
        return True

    await client.send_message(msg.chat.id, f"unknown op cmd: {cmd}")
    return True


def _parse_user(token: str) -> int | str:
    t = token.strip()
    if t.startswith("@"):
        return t[1:]
    try:
        return int(t)
    except ValueError:
        return t


def _tool_catalog(ctx: ToolContext) -> str:
    """Render a compact catalog for the operator LLM."""
    reg = build_registry(ctx)
    lines: list[str] = []
    for spec in reg.select():
        lines.append(f"- {spec.name}: {spec.description}")
    return "\n".join(lines)


async def _handle_nl(
    client: Client, msg: Message, body: str, *, ctx: ToolContext, settings: Settings
) -> bool:
    """LLM-classify the message as command-or-chat; if command, run tool calls."""
    friend_first_name = (msg.from_user.first_name or "друг").strip() if msg.from_user else "друг"
    p = ctx.persona
    persona_voice = (
        f"{p.identity.name}, {p.identity.age}, {p.identity.city}. "
        f"register={p.speech.speech_register}, humor={p.derived.get('humor_style','dry')}, "
        f"caps={p.speech.uses_caps}, emoji={p.speech.uses_emoji}, punctuation={p.speech.punctuation}. "
        f"avg sentence ≈ {p.speech.sentence_length_avg} words. "
        f"top traits: " + ", ".join(
            f"{k}={v:.2f}" for k, v in sorted(p.traits.items(), key=lambda kv: -kv[1])[:6]
        )
    )
    sys = render(
        "operator_intent.j2",
        tool_catalog=_tool_catalog(ctx),
        current_chat_id=msg.chat.id,
        operator_id=settings.operator_id,
        friend_first_name=friend_first_name,
        persona_voice=persona_voice,
    )
    recent_block = await _recent_messages_block(ctx, msg.chat.id, settings.operator_id)
    user_payload = body if not recent_block else f"{body}\n\n[recent_messages]\n{recent_block}"
    try:
        out = await think_json(
            [
                {"role": "system", "content": sys},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.2, max_tokens=500,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        log.warning("operator NL classify failed: {}", e)
        return False

    if out.get("kind") != "command":
        return False

    calls = out.get("calls") or []
    if not calls:
        return False

    reg = build_registry(ctx)
    by_name = {t.name: t for t in reg.select()}
    results: list[dict] = []
    for call in calls:
        name = str(call.get("tool", "")).strip()
        args = call.get("args") or {}
        spec = by_name.get(name)
        if spec is None:
            results.append({"tool": name, "error": "unknown tool"})
            continue
        try:
            res = await spec.fn(args)
        except Exception as e:
            res = {"error": f"{type(e).__name__}: {e}"}
        results.append({"tool": name, "args": args, "result": res})

    final_lines = await _compose_operator_reply(
        ctx, body, out.get("reply") or "", results, friend_first_name,
    )
    await _send_with_typing(client, msg.chat.id, final_lines)
    try:
        await client.read_chat_history(msg.chat.id)
    except Exception:
        pass
    return True


async def _recent_messages_block(ctx: ToolContext, chat_id: int, operator_id: int) -> str:
    """Compact dump of the last few messages in this chat, with msg ids, for the classifier."""
    try:
        rows = await ctx.memory.repos.archive.recent(chat_id, limit=12)
    except Exception:
        return ""
    lines: list[str] = []
    for row in rows[-12:]:
        text = (row.text or row.caption or "").replace("\n", " ").strip()
        if not text and row.kind != "text":
            text = f"<{row.kind}>"
        if len(text) > 160:
            text = text[:160] + "…"
        who = "me" if row.is_self else (
            "friend" if row.from_id == operator_id else f"u{row.from_id}"
        )
        lines.append(f"msg_id={row.tg_msg_id} from={who}: {text}")
    return "\n".join(lines)



async def _compose_operator_reply(
    ctx: ToolContext, user_msg: str, draft_reply: str,
    results: list[dict], friend_first_name: str,
) -> list[str]:
    """Second LLM pass: turn tool results into a natural multi-message answer."""
    p = ctx.persona
    persona_voice = (
        f"{p.identity.name}, {p.identity.age}, {p.identity.city}. "
        f"register={p.speech.speech_register}, humor={p.derived.get('humor_style','dry')}, "
        f"caps={p.speech.uses_caps}, emoji={p.speech.uses_emoji}, punctuation={p.speech.punctuation}. "
        f"sentence ≈ {p.speech.sentence_length_avg} words."
    )
    payload = orjson.dumps(
        [{"tool": r["tool"], "result": r.get("result") or r.get("error") or {}} for r in results],
        option=orjson.OPT_INDENT_2,
    ).decode()[:4000]
    sys_p = (
        "You are the persona answering a single trusted friend in his DM. He just asked you to do or look up "
        "something, and you ran the tools. Now write a short multi-message answer in HER voice. "
        f"PERSONA: {persona_voice}\n"
        f"FRIEND_NAME: {friend_first_name}.\n"
        "Rules:\n"
        "- NEVER paste raw JSON or tool names or fields like 'items', 'count', 'chat_id'. The friend doesn't see machinery.\n"
        "- Speak as a person: 'я ей написала', 'пока тихо', 'разобралась'.\n"
        "- If results are empty (e.g. no messages yet) — say it naturally, in 1-2 short bubbles. Don't pretend something happened.\n"
        "- Split into 1-4 short messages (Telegram style), as if a real person typing in bursts.\n"
        "- Match her humor and tone. NO meta-words like 'tool', 'operator', 'AI', 'response_format', 'json'.\n"
        "Output STRICT JSON: {\"messages\": [\"...\", \"...\"]}."
    )
    usr_p = orjson.dumps({
        "friend_message": user_msg,
        "my_draft_intent": draft_reply,
        "tool_results": results,
    }, option=orjson.OPT_INDENT_2).decode()
    try:
        comp = await think_json(
            [{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
            temperature=0.7, max_tokens=600,
        )
        msgs = comp.get("messages") or []
        out = [str(m).strip() for m in msgs if str(m).strip()]
        if out:
            return out[:6]
    except Exception as e:
        log.warning("compose_operator_reply failed: {}", e)
    if draft_reply.strip():
        return [draft_reply.strip()]
    return ["окей, сделала"]


async def _send_with_typing(client: Client, chat_id: int, messages: list[str]) -> None:
    """Send 1..N messages with realistic typing (with interruptions on long bursts)."""
    from pyrogram.enums import ChatAction
    from azura.humanize.typing import type_with_ticks
    import asyncio as _asyncio
    import random as _random
    if not messages:
        return

    async def _ping():
        try:
            await client.send_chat_action(chat_id, ChatAction.TYPING)
        except Exception:
            pass

    for idx, text in enumerate(messages):
        text = (text or "").strip()
        if not text:
            continue
        chars = len(text)
        type_s = max(0.8, min(7.0, chars / 18.0)) * _random.uniform(0.75, 1.35)
        log.info("op typing burst chat={} chars={} secs={:.1f}", chat_id, chars, type_s)
        await type_with_ticks(
            chat_id=chat_id, total_seconds=type_s, keepalive=lambda _cid: _ping(),
        )
        await client.send_message(chat_id, text)
        if idx + 1 < len(messages):
            next_len = len(messages[idx + 1])
            gap = max(0.4, min(2.5, next_len / 70.0)) * _random.uniform(0.6, 1.5)
            await _asyncio.sleep(gap)


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
