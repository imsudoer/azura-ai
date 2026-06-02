"""Disk media cache: download incoming photos/voices/etc into data/media_cache/.

The kurigram file_id can expire — keeping a local copy preserves long-term
context for the persona. Size-bounded LRU eviction protects the disk.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message

from azura.config import get_settings
from azura.utils.log import get_logger

log = get_logger("tg.media_cache")


_EXT_BY_KIND = {
    "photo": ".jpg",
    "video": ".mp4",
    "animation": ".mp4",
    "voice": ".ogg",
    "audio": ".mp3",
    "document": ".bin",
    "video_note": ".mp4",
    "sticker": ".webp",
}


def _chat_dir(chat_id: int) -> Path:
    s = get_settings()
    p = s.media_cache_dir / str(chat_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _candidate_filename(chat_id: int, tg_msg_id: int, kind: str, original_name: str | None) -> Path:
    base = f"{tg_msg_id}"
    if original_name:
        ext = Path(original_name).suffix or _EXT_BY_KIND.get(kind, ".bin")
        return _chat_dir(chat_id) / f"{base}{ext}"
    return _chat_dir(chat_id) / f"{base}{_EXT_BY_KIND.get(kind, '.bin')}"


async def download_media(client: Client, msg: Message, kind: str) -> Path | None:
    """Download msg media into the cache; returns local path or None on failure / oversize."""
    s = get_settings()
    if not _has_media(msg):
        return None
    size = _media_size(msg)
    if size and size > s.media_max_download_mb * 1024 * 1024:
        log.info("skip media chat={} msg={} oversize={}", msg.chat.id, msg.id, size)
        return None
    original_name = _file_name(msg)
    out = _candidate_filename(msg.chat.id, msg.id, kind, original_name)
    if out.exists():
        return out
    try:
        path = await client.download_media(msg, file_name=str(out))
        if not path:
            return None
        return Path(path)
    except Exception as e:
        log.warning("download_media failed chat={} msg={}: {}", msg.chat.id, msg.id, e)
        return None


def _has_media(msg: Message) -> bool:
    return any(getattr(msg, k, None) for k in (
        "photo", "video", "animation", "voice", "audio", "document", "video_note", "sticker",
    ))


def _media_size(msg: Message) -> int | None:
    for attr in ("video", "animation", "voice", "audio", "document", "video_note"):
        obj = getattr(msg, attr, None)
        if obj is not None and getattr(obj, "file_size", None):
            return int(obj.file_size)
    if msg.photo and getattr(msg.photo, "file_size", None):
        return int(msg.photo.file_size)
    return None


def _file_name(msg: Message) -> str | None:
    for attr in ("audio", "document", "video"):
        obj = getattr(msg, attr, None)
        if obj is not None and getattr(obj, "file_name", None):
            return str(obj.file_name)
    return None


def enforce_cache_quota(*, max_mb: int = 2048) -> int:
    """LRU-evict the oldest cached files until total size <= max_mb. Returns bytes freed."""
    s = get_settings()
    root = s.media_cache_dir
    if not root.exists():
        return 0
    files: list[tuple[Path, float, int]] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        files.append((p, st.st_atime, st.st_size))
    total = sum(sz for _, _, sz in files)
    cap = max_mb * 1024 * 1024
    if total <= cap:
        return 0
    files.sort(key=lambda x: x[1])
    freed = 0
    for p, _, sz in files:
        if total - freed <= cap:
            break
        try:
            p.unlink()
            freed += sz
        except OSError:
            continue
    log.info("media_cache evicted {} bytes ({} mb)", freed, freed // (1024 * 1024))
    return freed


def touch(path: Path) -> None:
    """Update atime so LRU keeps in-use files."""
    try:
        now = time.time()
        os.utime(path, (now, path.stat().st_mtime))
    except OSError:
        pass
