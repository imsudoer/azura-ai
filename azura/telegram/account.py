"""Account-level operations: profile, username, about, photo, block, privacy."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pyrogram import Client
from pyrogram.enums import BlockList, PrivacyKey
from pyrogram.raw import types as raw_types

from azura.utils.log import get_logger

log = get_logger("tg.account")


PRIVACY_KEYS: dict[str, PrivacyKey] = {
    "status": PrivacyKey.STATUS,
    "last_seen": PrivacyKey.STATUS,
    "profile_photo": PrivacyKey.PROFILE_PHOTO,
    "photo": PrivacyKey.PROFILE_PHOTO,
    "about": PrivacyKey.ABOUT,
    "bio": PrivacyKey.ABOUT,
    "forwards": PrivacyKey.FORWARDS,
    "phone_number": PrivacyKey.PHONE_NUMBER,
    "phone_call": PrivacyKey.PHONE_CALL,
    "phone_p2p": PrivacyKey.PHONE_P2P,
    "added_by_phone": PrivacyKey.ADDED_BY_PHONE,
    "chat_invite": PrivacyKey.CHAT_INVITE,
    "voice_messages": PrivacyKey.VOICE_MESSAGES,
    "birthday": PrivacyKey.BIRTHDAY,
}

VISIBILITY_PRESETS = ("everybody", "contacts", "nobody", "close_friends")


async def update_profile(
    client: Client,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    bio: str | None = None,
) -> dict:
    """Update first/last name and/or about line."""
    ok = await client.update_profile(
        first_name=first_name, last_name=last_name, bio=bio,
    )
    log.info("update_profile ok={} fn={} ln={} bio_len={}",
             ok, first_name, last_name, len(bio) if bio else 0)
    return {"ok": bool(ok)}


async def set_username(client: Client, username: str | None) -> dict:
    """Set or clear the username (pass None to clear)."""
    if username is not None:
        if not await client.check_username(username):
            return {"ok": False, "reason": "username unavailable"}
    ok = await client.set_username(username)
    return {"ok": bool(ok), "username": username}


async def set_profile_photo(client: Client, photo_path: str | Path) -> dict:
    """Set the profile photo from a local file path."""
    p = str(photo_path)
    ok = await client.set_profile_photo(photo=p)
    return {"ok": bool(ok), "photo": p}


async def delete_profile_photos(client: Client, photo_ids: list[str] | None = None) -> dict:
    """Delete some or all profile photos."""
    ok = await client.delete_profile_photos(photo_ids=photo_ids or [])
    return {"ok": bool(ok)}


async def block(client: Client, user_id: int | str) -> dict:
    """Block a user."""
    ok = await client.block_user(user_id)
    log.info("blocked user={} ok={}", user_id, ok)
    return {"ok": bool(ok), "user_id": str(user_id)}


async def unblock(client: Client, user_id: int | str) -> dict:
    """Unblock a user."""
    ok = await client.unblock_user(user_id)
    log.info("unblocked user={} ok={}", user_id, ok)
    return {"ok": bool(ok), "user_id": str(user_id)}


async def blocked_list(client: Client, limit: int = 100) -> list[int]:
    """Return current main blocklist as user ids."""
    out: list[int] = []
    async for c in client.get_blocked_message_senders(block_list=BlockList.MAIN, limit=limit):
        out.append(c.id)
    return out


def _build_rules(
    *,
    base: str = "everybody",
    allow_users: list[int] | None = None,
    disallow_users: list[int] | None = None,
) -> list[Any]:
    """Build privacy rule list. Order matters in TG: AllowUsers/DisallowUsers override base."""
    rules: list[Any] = []
    if disallow_users:
        rules.append(raw_types.InputPrivacyValueDisallowUsers(
            users=[raw_types.InputUser(user_id=uid, access_hash=0) for uid in disallow_users]
        ))
    if allow_users:
        rules.append(raw_types.InputPrivacyValueAllowUsers(
            users=[raw_types.InputUser(user_id=uid, access_hash=0) for uid in allow_users]
        ))
    if base == "everybody":
        rules.append(raw_types.InputPrivacyValueAllowAll())
    elif base == "contacts":
        rules.append(raw_types.InputPrivacyValueAllowContacts())
    elif base == "close_friends":
        rules.append(raw_types.InputPrivacyValueAllowCloseFriends())
    elif base == "nobody":
        rules.append(raw_types.InputPrivacyValueDisallowAll())
    else:
        rules.append(raw_types.InputPrivacyValueAllowAll())
    return rules


async def set_privacy(
    client: Client,
    *,
    key: str,
    base: str = "everybody",
    allow_users: list[int] | None = None,
    disallow_users: list[int] | None = None,
) -> dict:
    """Set a privacy key with optional per-user overrides.

    Example: key='status', base='everybody', disallow_users=[12345] →
    everybody sees online except user 12345 who sees 'recently'.
    """
    if key not in PRIVACY_KEYS:
        return {"ok": False, "reason": f"unknown privacy key '{key}'"}
    if base not in VISIBILITY_PRESETS:
        return {"ok": False, "reason": f"unknown base '{base}'"}
    pk = PRIVACY_KEYS[key]
    rules = _build_rules(base=base, allow_users=allow_users, disallow_users=disallow_users)
    needs_raw_rules = bool(allow_users) or bool(disallow_users)
    try:
        if needs_raw_rules:
            await _set_privacy_raw(client, pk, rules)
        else:
            await client.set_privacy(pk, rules=rules)
    except Exception as e:
        log.warning("set_privacy failed key={}: {}", key, e)
        return {"ok": False, "reason": str(e)}
    return {
        "ok": True, "key": key, "base": base,
        "allow_users": allow_users or [], "disallow_users": disallow_users or [],
    }


async def _set_privacy_raw(client: Client, pk: PrivacyKey, rules: list[Any]) -> None:
    """Fallback for raw privacy rules when set_privacy() chokes on InputPrivacyValueDisallowUsers."""
    from pyrogram.raw.functions.account import SetPrivacy
    await client.invoke(SetPrivacy(key=pk.value(), rules=rules))


async def get_privacy(client: Client, key: str) -> dict:
    """Inspect current rules for a key."""
    if key not in PRIVACY_KEYS:
        return {"ok": False, "reason": f"unknown privacy key '{key}'"}
    pk = PRIVACY_KEYS[key]
    try:
        rules = await client.get_privacy(pk)
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    return {"ok": True, "key": key, "rules": [_describe_rule(r) for r in rules]}


def _describe_rule(rule: Any) -> dict:
    """Best-effort human description of a returned privacy rule."""
    name = type(rule).__name__
    out: dict = {"type": name}
    for attr in ("users", "chats"):
        v = getattr(rule, attr, None)
        if v is not None:
            out[attr] = [getattr(x, "id", x) for x in v]
    return out
