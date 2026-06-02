"""Push the persona's internal presence into the Telegram account status.

Telegram userbots are shown "online" as long as they're consuming updates. To
actually appear offline / inactive on the recipient's side we need to send a raw
`account.updateStatus(offline=True)` request. The latest call wins for the
"last seen" semantics.
"""
from __future__ import annotations

from pyrogram import Client
from pyrogram.raw.functions.account import UpdateStatus

from azura.constants import Presence
from azura.utils.log import get_logger

log = get_logger("tg.presence")


_VISIBLE_ONLINE = {Presence.ONLINE, Presence.BUSY}


async def apply_to_telegram(client: Client, state: Presence) -> None:
    """Push the given persona state to the Telegram account.

    Online for ONLINE/BUSY; offline for ASLEEP/OFFLINE/AFK.
    """
    if client is None:
        return
    offline = state not in _VISIBLE_ONLINE
    try:
        await client.invoke(UpdateStatus(offline=offline))
        log.info("tg account status \u2192 {} ({})", "online" if not offline else "offline", state.value)
    except Exception as e:
        log.warning("UpdateStatus failed: {}", e)
