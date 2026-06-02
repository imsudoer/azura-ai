"""Shared context object every tool receives."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from azura.memory.service import MemoryService
from azura.mind.conflict import ConflictEngine
from azura.mind.mood import MoodEngine
from azura.mind.presence import PresenceEngine
from azura.mind.tails import TailQueue
from azura.personality.schema import Persona


@dataclass
class ToolContext:
    """Everything a tool implementation might need."""
    persona: Persona
    memory: MemoryService
    mood: MoodEngine
    presence: PresenceEngine
    conflict: ConflictEngine
    tails: TailQueue
    chat_id: int | None = None
    user_id: int | None = None
    sender: Callable[[int, list[str], dict[str, Any]], Awaitable[dict]] | None = None
    sticker_sender: Callable[[int, str], Awaitable[dict]] | None = None
    gif_sender: Callable[[int, str], Awaitable[dict]] | None = None
    media_sender: Callable[[int, str, str], Awaitable[dict]] | None = None
    web_searcher: Callable[[str], Awaitable[list[dict]]] | None = None
    web_fetcher: Callable[[str], Awaitable[str]] | None = None
    _tg_client: Any = None
