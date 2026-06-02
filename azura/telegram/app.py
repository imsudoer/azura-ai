"""Build the userbot `Client` instance from Settings."""
from __future__ import annotations

from pathlib import Path

from pyrogram import Client

from azura.config import Settings
from azura.telegram.patches import apply as apply_patches


def make_client(s: Settings) -> Client:
    """Construct a kurigram userbot client (no bot token, file session)."""
    apply_patches()
    workdir = Path(s.session_path).parent
    workdir.mkdir(parents=True, exist_ok=True)
    name = s.tg_session_name
    return Client(
        name=name,
        api_id=s.tg_api_id,
        api_hash=s.tg_api_hash,
        workdir=str(workdir),
        in_memory=False,
        sleep_threshold=30,
        max_concurrent_transmissions=2,
    )
