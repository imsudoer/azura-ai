"""Patches for kurigram quirks (apply once on import)."""
from __future__ import annotations

from pyrogram import utils as _pyutils


def _get_peer_type_new(peer_id: int) -> str:
    """Pick the peer type for a raw id; tolerant to channel/super/user encodings."""
    s = str(peer_id)
    if not s.startswith("-"):
        return "user"
    if s.startswith("-100"):
        return "channel"
    return "chat"


def apply() -> None:
    """Idempotently apply all known kurigram patches."""
    _pyutils.get_peer_type = _get_peer_type_new
