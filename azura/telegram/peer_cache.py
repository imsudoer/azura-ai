"""In-memory peer cache that prevents resolve_peer calls to Telegram when offline.

Root cause of "she's online every minute": pyrogram calls resolve_peer for
each read_chat_history / get_chat_member / etc., and EVERY MTProto RPC counts
as "user activity" on the Telegram server → she shows as "online" for ~30s.

This module monkey-patches client.resolve_peer to:
  1. Cache every resolved peer forever (they rarely change).
  2. If the peer is not cached AND we're outside an explicit online window,
     SKIP the real resolve (raise KeyError → caller handles gracefully or
     we return a minimal InputPeerChat/InputPeerUser from chat_id sign).
  3. If we're inside an online window, do a real resolve and cache.

Also patches read_chat_history and get_chat_member to silently return None
when offline and peer is unknown, instead of leaking online status.
"""
from __future__ import annotations

import time

from pyrogram import Client
from pyrogram.raw.types import InputPeerChat, InputPeerUser, InputPeerChannel

from azura.utils.log import get_logger

log = get_logger("tg.peer_cache")

_cache: dict[int, object] = {}


def _guess_peer(chat_id: int):
    """Build a minimal InputPeer from the chat_id sign convention."""
    if chat_id > 0:
        return InputPeerUser(user_id=chat_id, access_hash=0)
    raw = -chat_id
    if raw > 1000000000000:
        return InputPeerChannel(channel_id=raw - 1000000000000, access_hash=0)
    return InputPeerChat(chat_id=raw)


def install_peer_cache(client: Client) -> None:
    """Monkey-patch resolve_peer + guard read_chat_history / get_chat_member."""

    _original_resolve = client.resolve_peer
    _original_read = client.read_chat_history
    _original_get_member = getattr(client, "get_chat_member", None)

    async def _cached_resolve_peer(peer_id):
        if peer_id in _cache:
            return _cache[peer_id]

        from azura.telegram.tg_presence import _online_until
        now = time.monotonic()
        if now < _online_until:
            result = await _original_resolve(peer_id)
            _cache[peer_id] = result
            log.info("peer resolved (online window) id={}", peer_id)
            return result

        guessed = _guess_peer(int(peer_id))
        log.debug("peer guessed (offline) id={} -> {}", peer_id, type(guessed).__name__)
        return guessed

    async def _guarded_read_chat_history(chat_id, *args, **kwargs):
        from azura.telegram.tg_presence import _online_until
        now = time.monotonic()
        if now < _online_until:
            return await _original_read(chat_id, *args, **kwargs)

        if chat_id in _cache:
            return await _original_read(chat_id, *args, **kwargs)

        log.debug("read_chat_history SKIPPED (offline, no cached peer) chat={}", chat_id)
        return None

    async def _guarded_get_chat_member(chat_id, user_id, *args, **kwargs):
        if _original_get_member is None:
            return None
        from azura.telegram.tg_presence import _online_until
        now = time.monotonic()
        if now >= _online_until and chat_id not in _cache:
            log.debug("get_chat_member SKIPPED (offline) chat={} user={}", chat_id, user_id)
            return None
        return await _original_get_member(chat_id, user_id, *args, **kwargs)

    client.resolve_peer = _cached_resolve_peer
    client.read_chat_history = _guarded_read_chat_history
    if _original_get_member is not None:
        client.get_chat_member = _guarded_get_chat_member

    log.info("peer cache installed — resolve_peer cached, read/get_member guarded when offline")


def warm_cache(client: Client, chat_ids: list[int]) -> None:
    """Pre-warm cache during boot (when we're briefly online)."""
    import asyncio

    async def _warm():
        for cid in chat_ids:
            try:
                peer = await client.resolve_peer(cid)
                _cache[cid] = peer
            except Exception:
                pass
        log.info("peer cache warmed: {} entries", len(_cache))

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_warm())
    except RuntimeError:
        pass
