"""Tools for managing the userbot account: profile, username, about, photo, block."""
from __future__ import annotations

from pathlib import Path

from azura.mind.agent import ToolSpec
from azura.telegram import account as acct
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Account-management tool specs. Need ctx._client to be bound."""

    client = getattr(ctx, "_tg_client", None)

    async def update_profile(args: dict) -> dict:
        if client is None:
            return {"error": "tg client not bound"}
        return await acct.update_profile(
            client,
            first_name=args.get("first_name"),
            last_name=args.get("last_name"),
            bio=args.get("bio"),
        )

    async def set_username(args: dict) -> dict:
        if client is None:
            return {"error": "tg client not bound"}
        return await acct.set_username(client, args.get("username"))

    async def set_profile_photo(args: dict) -> dict:
        if client is None:
            return {"error": "tg client not bound"}
        p = args.get("photo_path")
        if not p or not Path(p).exists():
            return {"error": f"path missing: {p}"}
        return await acct.set_profile_photo(client, p)

    async def delete_profile_photos(args: dict) -> dict:
        if client is None:
            return {"error": "tg client not bound"}
        return await acct.delete_profile_photos(client, args.get("photo_ids"))

    async def block_user(args: dict) -> dict:
        if client is None:
            return {"error": "tg client not bound"}
        return await acct.block(client, args["user_id"])

    async def unblock_user(args: dict) -> dict:
        if client is None:
            return {"error": "tg client not bound"}
        return await acct.unblock(client, args["user_id"])

    async def list_blocked(_: dict) -> dict:
        if client is None:
            return {"error": "tg client not bound"}
        ids = await acct.blocked_list(client)
        return {"ids": ids}

    return [
        make_spec("update_profile",
                  "Update profile first name / last name / bio (about).",
                  {"type": "object", "properties": {
                      "first_name": {"type": "string"},
                      "last_name": {"type": "string"},
                      "bio": {"type": "string"}}},
                  update_profile),
        make_spec("set_username",
                  "Change @username (pass null to clear). Checks availability first.",
                  {"type": "object", "required": ["username"], "properties": {
                      "username": {"type": ["string", "null"]}}},
                  set_username),
        make_spec("set_profile_photo",
                  "Set profile photo from a local file path.",
                  {"type": "object", "required": ["photo_path"], "properties": {
                      "photo_path": {"type": "string"}}},
                  set_profile_photo),
        make_spec("delete_profile_photos",
                  "Delete profile photos (by ids, or all if empty).",
                  {"type": "object", "properties": {
                      "photo_ids": {"type": "array", "items": {"type": "string"}}}},
                  delete_profile_photos),
        make_spec("block_user",
                  "Block a user by id or username.",
                  {"type": "object", "required": ["user_id"], "properties": {
                      "user_id": {"type": ["integer", "string"]}}},
                  block_user),
        make_spec("unblock_user",
                  "Unblock a user.",
                  {"type": "object", "required": ["user_id"], "properties": {
                      "user_id": {"type": ["integer", "string"]}}},
                  unblock_user),
        make_spec("list_blocked",
                  "List currently blocked users.",
                  {"type": "object", "properties": {}},
                  list_blocked),
    ]
