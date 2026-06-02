"""Tools for general + per-user privacy overrides. Persisted into kv for stable replay."""
from __future__ import annotations

from azura.mind.agent import ToolSpec
from azura.telegram import account as acct
from azura.tools.context import ToolContext
from azura.tools.registry import make_spec


def _kv_key(category: str) -> str:
    """Stable kv key for a privacy category."""
    return f"privacy:{category}"


async def _load(ctx: ToolContext, category: str) -> dict:
    raw = await ctx.memory.repos.kv.get_json(_kv_key(category))
    if not isinstance(raw, dict):
        return {"base": "everybody", "allow_users": [], "disallow_users": []}
    return raw


async def _save(ctx: ToolContext, category: str, state: dict) -> None:
    await ctx.memory.repos.kv.set_json(_kv_key(category), state)


async def _apply(ctx: ToolContext, client, category: str, state: dict) -> dict:
    res = await acct.set_privacy(
        client, key=category,
        base=state.get("base", "everybody"),
        allow_users=state.get("allow_users") or [],
        disallow_users=state.get("disallow_users") or [],
    )
    if res.get("ok"):
        await _save(ctx, category, state)
    return res


def build(ctx: ToolContext) -> list[ToolSpec]:
    """Privacy tools that combine TG calls with persistent overrides in kv."""

    client = getattr(ctx, "_tg_client", None)

    async def set_privacy_general(args: dict) -> dict:
        """Set baseline visibility for a privacy category."""
        if client is None:
            return {"error": "tg client not bound"}
        category = str(args["category"]).lower()
        if category not in acct.PRIVACY_KEYS:
            return {"error": f"unknown category {category}"}
        state = await _load(ctx, category)
        state["base"] = str(args.get("base", "everybody"))
        return await _apply(ctx, client, category, state)

    async def hide_from_user(args: dict) -> dict:
        """Hide a privacy attribute from a specific user (e.g. set last-seen to 'recently')."""
        if client is None:
            return {"error": "tg client not bound"}
        category = str(args["category"]).lower()
        if category not in acct.PRIVACY_KEYS:
            return {"error": f"unknown category {category}"}
        uid = int(args["user_id"])
        state = await _load(ctx, category)
        if uid not in state["disallow_users"]:
            state["disallow_users"].append(uid)
        if uid in state["allow_users"]:
            state["allow_users"].remove(uid)
        return await _apply(ctx, client, category, state)

    async def show_to_user(args: dict) -> dict:
        """Force a privacy attribute visible to a specific user (overrides base)."""
        if client is None:
            return {"error": "tg client not bound"}
        category = str(args["category"]).lower()
        if category not in acct.PRIVACY_KEYS:
            return {"error": f"unknown category {category}"}
        uid = int(args["user_id"])
        state = await _load(ctx, category)
        if uid not in state["allow_users"]:
            state["allow_users"].append(uid)
        if uid in state["disallow_users"]:
            state["disallow_users"].remove(uid)
        return await _apply(ctx, client, category, state)

    async def reset_user_override(args: dict) -> dict:
        """Drop a per-user override; user follows the base rule again."""
        if client is None:
            return {"error": "tg client not bound"}
        category = str(args["category"]).lower()
        if category not in acct.PRIVACY_KEYS:
            return {"error": f"unknown category {category}"}
        uid = int(args["user_id"])
        state = await _load(ctx, category)
        if uid in state["allow_users"]:
            state["allow_users"].remove(uid)
        if uid in state["disallow_users"]:
            state["disallow_users"].remove(uid)
        return await _apply(ctx, client, category, state)

    async def show_privacy(args: dict) -> dict:
        """Return the persisted privacy state + live TG rules for a category."""
        if client is None:
            return {"error": "tg client not bound"}
        category = str(args["category"]).lower()
        state = await _load(ctx, category)
        live = await acct.get_privacy(client, category)
        return {"persisted": state, "live": live}

    return [
        make_spec("set_privacy_general",
                  "Set baseline visibility for a privacy category (everybody/contacts/close_friends/nobody).",
                  {"type": "object", "required": ["category", "base"], "properties": {
                      "category": {"type": "string"},
                      "base": {"type": "string", "enum": ["everybody", "contacts", "close_friends", "nobody"]}}},
                  set_privacy_general),
        make_spec("hide_from_user",
                  "Hide a privacy attribute from one user (e.g. their view of your online status becomes 'recently').",
                  {"type": "object", "required": ["category", "user_id"], "properties": {
                      "category": {"type": "string"},
                      "user_id": {"type": "integer"}}},
                  hide_from_user),
        make_spec("show_to_user",
                  "Force a privacy attribute visible to one user (overrides base).",
                  {"type": "object", "required": ["category", "user_id"], "properties": {
                      "category": {"type": "string"},
                      "user_id": {"type": "integer"}}},
                  show_to_user),
        make_spec("reset_user_override",
                  "Remove a per-user privacy override.",
                  {"type": "object", "required": ["category", "user_id"], "properties": {
                      "category": {"type": "string"},
                      "user_id": {"type": "integer"}}},
                  reset_user_override),
        make_spec("show_privacy",
                  "Show persisted + live privacy state for a category.",
                  {"type": "object", "required": ["category"], "properties": {
                      "category": {"type": "string"}}},
                  show_privacy),
    ]
