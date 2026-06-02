"""Online/offline mirror: keep the userbot's TG presence in sync with PresenceEngine."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.raw import functions

from azura.constants import Presence
from azura.mind.presence import PresenceView
from azura.utils.log import get_logger

log = get_logger("tg.online")


async def push_status(client: Client, view: PresenceView) -> None:
    """Map a PresenceView to a TG online/offline raw call."""
    offline = view.state in (Presence.OFFLINE, Presence.ASLEEP)
    try:
        await client.invoke(functions.account.UpdateStatus(offline=offline))
    except Exception as e:
        log.warning("status push failed: {}", e)


def is_reachable(view: PresenceView) -> bool:
    """Whether the persona is currently able to read/send."""
    return view.is_reachable
