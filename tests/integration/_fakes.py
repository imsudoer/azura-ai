"""Fakes for kurigram Client + LLM, narrow enough for integration tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class FakeChatAction:
    TYPING = "typing"


@dataclass
class FakeUser:
    id: int
    first_name: str = "X"
    last_name: str | None = None
    username: str | None = None
    is_bot: bool = False


@dataclass
class FakeChat:
    id: int
    type: Any
    title: str | None = None
    username: str | None = None


@dataclass
class FakeMessage:
    id: int
    chat: FakeChat
    from_user: FakeUser | None
    text: str | None = None
    caption: str | None = None
    date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    outgoing: bool = False
    reply_to_message_id: int | None = None
    reply_to_message: "FakeMessage | None" = None
    sticker: Any = None
    animation: Any = None
    photo: Any = None
    video: Any = None
    voice: Any = None


@dataclass
class FakeSentMessage:
    id: int


class FakeClient:
    """Records every outgoing call instead of hitting Telegram."""

    def __init__(self, me_id: int = 999, me_name: str = "Mira", me_username: str = "mira_xx") -> None:
        self._me = FakeUser(id=me_id, first_name=me_name, username=me_username)
        self.sent_messages: list[tuple[int, str, dict]] = []
        self.read_history_calls: list[int] = []
        self.typing_calls: list[int] = []
        self.reactions: list[tuple[int, int, str]] = []
        self.send_id = 10_000

    async def get_me(self):
        return self._me

    async def send_chat_action(self, chat_id: int, action: str) -> None:
        self.typing_calls.append(chat_id)

    async def send_message(self, chat_id: int, text: str, **kw) -> FakeSentMessage:
        self.send_id += 1
        self.sent_messages.append((chat_id, text, kw))
        return FakeSentMessage(id=self.send_id)

    async def send_sticker(self, chat_id: int, file_id: str) -> FakeSentMessage:
        self.send_id += 1
        self.sent_messages.append((chat_id, f"<sticker:{file_id}>", {}))
        return FakeSentMessage(id=self.send_id)

    async def send_animation(self, chat_id: int, src: str) -> FakeSentMessage:
        self.send_id += 1
        self.sent_messages.append((chat_id, f"<anim:{src}>", {}))
        return FakeSentMessage(id=self.send_id)

    async def send_photo(self, chat_id: int, src: str) -> FakeSentMessage:
        self.send_id += 1
        self.sent_messages.append((chat_id, f"<photo:{src}>", {}))
        return FakeSentMessage(id=self.send_id)

    async def send_video(self, chat_id: int, src: str) -> FakeSentMessage:
        self.send_id += 1
        self.sent_messages.append((chat_id, f"<video:{src}>", {}))
        return FakeSentMessage(id=self.send_id)

    async def send_document(self, chat_id: int, src: str) -> FakeSentMessage:
        self.send_id += 1
        self.sent_messages.append((chat_id, f"<doc:{src}>", {}))
        return FakeSentMessage(id=self.send_id)

    async def read_chat_history(self, chat_id: int) -> None:
        self.read_history_calls.append(chat_id)

    async def send_reaction(self, chat_id: int, msg_id: int, emoji: str) -> None:
        self.reactions.append((chat_id, msg_id, emoji))


class FakePyrogramChatType:
    PRIVATE = type("T", (), {"value": "private"})()
    GROUP = type("T", (), {"value": "group"})()
    SUPERGROUP = type("T", (), {"value": "supergroup"})()
    CHANNEL = type("T", (), {"value": "channel"})()
    BOT = type("T", (), {"value": "bot"})()
