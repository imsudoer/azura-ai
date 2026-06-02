"""Extract rich metadata from a kurigram Message and persist into messages + archive."""
from __future__ import annotations

from typing import Any

from pyrogram.types import Message

import asyncio

from azura.db.repo import Repos
from azura.llm.vision import describe_image
from azura.telegram import media_cache
from azura.utils.timez import ts
from azura.utils.log import get_logger

log = get_logger("tg.record")


_MEDIA_ATTRS = (
    "sticker", "animation", "photo", "video", "voice", "audio",
    "document", "video_note", "location", "venue", "contact", "poll",
)


def detect_kind(msg: Message) -> str:
    """Pick a single high-level kind string."""
    for a in _MEDIA_ATTRS:
        if getattr(msg, a, None):
            return a
    if msg.text:
        return "text"
    if _is_service(msg):
        return "service"
    return "other"


def _is_service(msg: Message) -> bool:
    return any(getattr(msg, k, None) for k in (
        "new_chat_members", "left_chat_member", "new_chat_title",
        "new_chat_photo", "delete_chat_photo", "pinned_message",
        "channel_chat_created", "group_chat_created",
    ))


def service_kind(msg: Message) -> str | None:
    for k in (
        "new_chat_members", "left_chat_member", "new_chat_title",
        "new_chat_photo", "delete_chat_photo", "pinned_message",
        "channel_chat_created", "group_chat_created",
    ):
        if getattr(msg, k, None):
            return k
    return None


def extract_reactions(msg: Message) -> list[dict]:
    """Pull reactions block into a JSONable list of {emoji,count,...}."""
    r = getattr(msg, "reactions", None)
    if r is None:
        return []
    out: list[dict] = []
    items = getattr(r, "reactions", None) or []
    for it in items:
        d: dict[str, Any] = {}
        emoji = getattr(it, "emoji", None) or getattr(getattr(it, "reaction", None), "emoticon", None)
        if emoji:
            d["emoji"] = emoji
        cnt = getattr(it, "count", None)
        if cnt is not None:
            d["count"] = int(cnt)
        if d:
            out.append(d)
    return out


def media_meta(msg: Message, kind: str) -> dict:
    """Return a compact JSONable dict of media metadata."""
    m: dict[str, Any] = {}
    obj = getattr(msg, kind, None)
    if obj is None:
        return m
    for attr in ("file_id", "file_unique_id", "file_size", "file_name",
                 "mime_type", "duration", "width", "height", "performer",
                 "title", "emoji", "set_name"):
        v = getattr(obj, attr, None)
        if v is not None:
            m[attr] = v
    if kind == "location" and obj:
        m["latitude"] = getattr(obj, "latitude", None)
        m["longitude"] = getattr(obj, "longitude", None)
    if kind == "contact" and obj:
        m["phone_number"] = getattr(obj, "phone_number", None)
        m["first_name"] = getattr(obj, "first_name", None)
        m["last_name"] = getattr(obj, "last_name", None)
    if kind == "poll" and obj:
        m["question"] = getattr(obj, "question", None)
        m["options"] = [getattr(o, "text", str(o)) for o in (getattr(obj, "options", None) or [])]
    return m


def primary_file_id(msg: Message, kind: str) -> str | None:
    """Return the most representative file_id for this kind."""
    obj = getattr(msg, kind, None)
    if obj is None:
        return None
    fid = getattr(obj, "file_id", None)
    return str(fid) if fid else None


def forward_ids(msg: Message) -> tuple[int | None, int | None]:
    """Return (forward_from_user_id, forward_from_chat_id)."""
    ff_user = getattr(msg, "forward_from", None)
    ff_chat = getattr(msg, "forward_from_chat", None)
    return (
        ff_user.id if ff_user is not None else None,
        ff_chat.id if ff_chat is not None else None,
    )


async def record_message(
    client,
    repos: Repos,
    msg: Message,
    *,
    chat_kind: str,
    is_self: bool = False,
    download_media_now: bool = True,
) -> tuple[int | None, int | None]:
    """Persist a message into both the hot ring and the never-trimmed archive.

    Returns (messages_row_id, archive_row_id) — either may be None on failure.
    """
    kind = detect_kind(msg)
    media_ref = primary_file_id(msg, kind) if kind in _MEDIA_ATTRS else None
    meta = media_meta(msg, kind) if kind in _MEDIA_ATTRS else {}
    text = msg.text or None
    caption = msg.caption or None
    media_group_id = getattr(msg, "media_group_id", None)
    ff_user, ff_chat = forward_ids(msg)
    reactions = extract_reactions(msg)
    svc = service_kind(msg) if kind in ("service", "other") else None

    await repos.chats.upsert(
        msg.chat.id, kind=chat_kind,
        title=getattr(msg.chat, "title", None),
        username=getattr(msg.chat, "username", None),
    )
    if msg.from_user:
        await repos.users.upsert(
            msg.from_user.id,
            username=msg.from_user.username,
            first_name=msg.from_user.first_name,
            last_name=msg.from_user.last_name,
            is_bot=bool(msg.from_user.is_bot),
        )

    msg_ts = int(msg.date.timestamp()) if msg.date else ts()

    hot = await repos.messages.add(
        chat_id=msg.chat.id, tg_msg_id=msg.id,
        from_id=(msg.from_user.id if msg.from_user else None),
        ts_=msg_ts,
        kind=kind,
        text=text or caption,
        reply_to=msg.reply_to_message_id if msg.reply_to_message_id else None,
        media_ref=media_ref, is_self=is_self,
        media_group_id=media_group_id,
        forward_from_id=ff_user, forward_from_chat_id=ff_chat,
        reactions=reactions, meta=meta,
    )

    archive = await repos.archive.add(
        chat_id=msg.chat.id, tg_msg_id=msg.id,
        from_id=(msg.from_user.id if msg.from_user else None),
        ts_=msg_ts,
        kind=kind, text=text, caption=caption,
        reply_to=msg.reply_to_message_id if msg.reply_to_message_id else None,
        is_self=is_self, media_group_id=media_group_id,
        forward_from_id=ff_user, forward_from_chat_id=ff_chat,
        media=meta, reactions=reactions, service_kind=svc,
    )

    if download_media_now and kind in ("photo", "video", "animation", "voice", "audio", "video_note", "document", "sticker"):
        try:
            path = await media_cache.download_media(client, msg, kind)
            if path:
                await repos.archive.attach_local_path(archive.id, str(path))
                if kind in ("photo", "sticker") and archive.description is None:
                    asyncio.create_task(_describe_async(archive.id, path, kind))
        except Exception:
            log.exception("media download/describe failed chat={} msg={}", msg.chat.id, msg.id)

    return (hot.id if hot else None, archive.id if archive else None)


async def _describe_async(archive_id: int, path, kind: str) -> None:
    """Background task: run vision describer + write description into archive."""
    from azura.db.engine import get_sessionmaker
    try:
        desc = await describe_image(path, hint=f"this is a telegram {kind}")
    except Exception:
        desc = None
    if not desc:
        return
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            r = Repos(session)
            await r.archive.attach_description(archive_id, desc)
            await session.commit()
    except Exception:
        log.exception("attach_description failed id={}", archive_id)
