"""Safely download a direct URL to a temp file and send it as media."""
from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pyrogram import Client

from azura.config import get_settings
from azura.utils.log import get_logger
from azura.utils.timez import ts

log = get_logger("tg.media")


_ALLOWED_SCHEMES = {"http", "https"}
_BLOCK_HOSTS = {"localhost", "0.0.0.0"}


def _is_private_ip(host: str) -> bool:
    """Check if host resolves to a private/loopback IP (SSRF defense)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for fam, *_, sa in infos:
        try:
            ip = ipaddress.ip_address(sa[0])
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return True
        except ValueError:
            continue
    return False


async def download(url: str) -> Path:
    """Stream a URL to media_cache with size cap, scheme allow-list and SSRF guard."""
    s = get_settings()
    p = urlparse(url)
    if p.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"scheme not allowed: {p.scheme}")
    host = p.hostname or ""
    if not host or host.lower() in _BLOCK_HOSTS:
        raise ValueError("host blocked")
    if _is_private_ip(host):
        raise ValueError("private/loopback host blocked")

    max_bytes = s.media_max_download_mb * 1024 * 1024
    suffix = Path(p.path).suffix or ".bin"
    out_path = s.media_cache_dir / f"dl_{ts()}_{abs(hash(url)) & 0xFFFFFFFF:x}{suffix}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    async with httpx.AsyncClient(timeout=s.web_fetch_timeout_s, follow_redirects=True) as cli:
        async with cli.stream("GET", url) as r:
            r.raise_for_status()
            ct_len = int(r.headers.get("content-length") or 0)
            if ct_len and ct_len > max_bytes:
                raise ValueError(f"content too large: {ct_len}")
            with out_path.open("wb") as f:
                async for chunk in r.aiter_bytes(64 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError("download exceeded size limit")
                    f.write(chunk)
    return out_path


async def send_url(client: Client, chat_id: int, url: str, kind: str = "auto") -> dict:
    """Download a URL and send it as the chosen kind of media."""
    path = await download(url)
    sfx = path.suffix.lower()
    if kind == "auto":
        if sfx in {".jpg", ".jpeg", ".png", ".webp"}:
            kind = "photo"
        elif sfx in {".mp4", ".mov", ".webm"}:
            kind = "video"
        elif sfx == ".gif":
            kind = "animation"
        else:
            kind = "document"
    if kind == "photo":
        msg = await client.send_photo(chat_id, str(path))
    elif kind == "video":
        msg = await client.send_video(chat_id, str(path))
    elif kind == "animation":
        msg = await client.send_animation(chat_id, str(path))
    else:
        msg = await client.send_document(chat_id, str(path))
    return {"ok": True, "msg_id": msg.id, "kind": kind, "path": str(path)}
