"""Build the agent user_prompt from incoming message + memory + chat archive."""
from __future__ import annotations

import orjson

from azura.db.models import ChatArchive
from azura.memory.service import MemoryService
from azura.mind.triggers import TriggerHit


def _summarize_archive_row(row: ChatArchive, *, max_text: int = 280) -> dict:
    """Compact JSONable summary of one archive row for the prompt."""
    out: dict = {
        "tg_msg_id": row.tg_msg_id,
        "from_id": row.from_id,
        "ts": row.ts,
        "kind": row.kind,
        "is_self": bool(row.is_self),
    }
    if row.text:
        out["text"] = row.text[:max_text]
    if row.caption:
        out["caption"] = row.caption[:max_text]
    if row.description:
        out["description"] = row.description[:max_text]
    if row.reactions:
        out["reactions"] = row.reactions
    if row.edited_ts:
        out["edited"] = True
    if row.deleted_ts:
        out["deleted"] = True
    if row.forward_from_id or row.forward_from_chat_id:
        out["forwarded_from"] = {
            "user_id": row.forward_from_id,
            "chat_id": row.forward_from_chat_id,
        }
    if row.media_group_id:
        out["album"] = row.media_group_id
    if row.service_kind:
        out["service"] = row.service_kind
    if row.kind in ("photo", "video", "animation", "voice", "audio", "video_note",
                    "document", "sticker", "location", "contact", "poll", "venue"):
        m = dict(row.media or {})
        out["media"] = {k: m[k] for k in ("emoji", "set_name", "duration", "width",
                                          "height", "mime_type", "file_name",
                                          "phone_number", "first_name", "question",
                                          "options")
                        if k in m}
    return out


def _collapse_albums(rows: list[ChatArchive]) -> list[dict]:
    """Group consecutive same-album rows into a single entry."""
    out: list[dict] = []
    seen_groups: set[str] = set()
    for r in rows:
        if r.media_group_id and r.media_group_id in seen_groups:
            tail = out[-1]
            tail.setdefault("album_size", 1)
            tail["album_size"] += 1
            if r.caption and "caption" not in tail:
                tail["caption"] = r.caption[:280]
            continue
        if r.media_group_id:
            seen_groups.add(r.media_group_id)
        out.append(_summarize_archive_row(r))
    return out


async def build_user_prompt(
    *,
    memory: MemoryService,
    chat_id: int,
    from_user_id: int | None,
    text: str,
    trigger: TriggerHit,
    in_private: bool,
    incoming_tg_msg_id: int | None = None,
    reply_to_text: str | None = None,
) -> str:
    """Compose a JSON situation block + the actual message text for the agent."""
    about = (
        await memory.recall_about_user(from_user_id, query=text)
        if from_user_id is not None else {}
    )
    chat_ctx = await memory.recall_chat(chat_id, limit_short=20, limit_long=8)

    reply_chain: list[dict] = []
    if incoming_tg_msg_id is not None:
        archive_chain = await memory.repos.archive.reply_chain(
            chat_id, incoming_tg_msg_id, max_depth=5
        )
        reply_chain = [_summarize_archive_row(r) for r in archive_chain
                       if r.tg_msg_id != incoming_tg_msg_id]

    recent = await memory.repos.archive.recent(chat_id, limit=40)
    timeline = _collapse_albums(recent)

    payload = {
        "chat": {
            "id": chat_id,
            "in_private": in_private,
            "opinion": chat_ctx.get("opinion"),
            "feelings": chat_ctx.get("feelings"),
            "recent_short_memory": chat_ctx.get("short", [])[-12:],
            "stable_facts": chat_ctx.get("long", [])[:8],
            "timeline_tail": timeline[-25:],
        },
        "user": about,
        "trigger": {
            "name_called": trigger.name_called,
            "username_mentioned": trigger.username_mentioned,
            "reply_to_self": trigger.reply_to_self,
            "keyword": trigger.keyword,
            "boundary_hit": trigger.boundary_hit,
        },
        "incoming": {
            "tg_msg_id": incoming_tg_msg_id,
            "text": text,
            "reply_to_text": reply_to_text,
            "reply_chain": reply_chain,
        },
    }
    return (
        "SITUATION JSON:\n"
        + orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode()
        + "\n\nCHECK timeline_tail FIRST: if you already replied to this conversation recently (is_self=true entries at the end), do NOT repeat the same greeting/answer. Continue naturally from where you left off."
        + "\nReact in character. Output messages only (no JSON, no preamble)."
    )
