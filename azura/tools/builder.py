"""Build a populated ToolRegistry with all tool families and tags."""
from __future__ import annotations

from azura.tools import (
    account_tools,
    chat_tools,
    gif_tools,
    media_tools,
    memory_tools,
    operator_tools,
    privacy_tools,
    self_tools,
    send_tools,
    sticker_tools,
    web_tools,
    world_tools,
)
from azura.tools.context import ToolContext
from azura.tools.registry import ToolRegistry


def build_registry(ctx: ToolContext) -> ToolRegistry:
    """Populate a registry with every tool family, tagged for situation-aware selection."""
    reg = ToolRegistry()
    for t in memory_tools.build(ctx):
        reg.add(t, "memory")
    for t in self_tools.build(ctx):
        reg.add(t, "self")
    for t in chat_tools.build(ctx):
        reg.add(t, "chat", "control")
    for t in send_tools.build(ctx):
        reg.add(t, "send")
    for t in sticker_tools.build(ctx):
        reg.add(t, "send", "media", "sticker")
    for t in gif_tools.build(ctx):
        reg.add(t, "send", "media", "gif")
    for t in media_tools.build(ctx):
        reg.add(t, "media")
    for t in web_tools.build(ctx):
        reg.add(t, "web")
    for t in operator_tools.build(ctx):
        reg.add(t, "operator")
    for t in account_tools.build(ctx):
        reg.add(t, "account", "self")
    for t in privacy_tools.build(ctx):
        reg.add(t, "privacy", "self")
    for t in world_tools.build(ctx):
        reg.add(t, "world", "chat")
    return reg


def default_tool_subset(reg: ToolRegistry) -> list:
    """Sensible default subset for an ordinary reply turn (no operator-only meta-tools)."""
    return reg.select(exclude_tags={"operator"})
