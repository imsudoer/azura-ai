"""SQLAlchemy ORM models for all persistent state."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base."""


class Chat(Base):
    """A telegram chat (private, group, channel)."""
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str | None] = mapped_column(String(256))
    username: Mapped[str | None] = mapped_column(String(64))
    importance: Mapped[int] = mapped_column(Integer, default=0)
    opinion: Mapped[int] = mapped_column(Integer, default=0)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_ts: Mapped[int] = mapped_column(BigInteger, default=0)
    first_contact_ts: Mapped[int] = mapped_column(BigInteger, default=0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class User(Base):
    """A peer the persona has seen."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), index=True)
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    opinion: Mapped[int] = mapped_column(Integer, default=0)
    first_contact_ts: Mapped[int] = mapped_column(BigInteger, default=0)
    last_seen_ts: Mapped[int] = mapped_column(BigInteger, default=0)
    interactions: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Message(Base):
    """Raw seen message buffer (per-chat ring)."""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), index=True)
    tg_msg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    from_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    ts: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="text")
    text: Mapped[str | None] = mapped_column(Text)
    reply_to: Mapped[int | None] = mapped_column(BigInteger)
    media_ref: Mapped[str | None] = mapped_column(String(256))
    is_self: Mapped[bool] = mapped_column(Boolean, default=False)
    seen: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("chat_id", "tg_msg_id", name="uq_chat_msg"),
        Index("ix_msg_chat_ts", "chat_id", "ts"),
    )


class MemoryItem(Base):
    """Generic memory entry across all tiers."""
    __tablename__ = "memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    topic: Mapped[str | None] = mapped_column(String(128), index=True)
    content: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    decay: Mapped[float] = mapped_column(Float, default=0.0)
    ts: Mapped[int] = mapped_column(BigInteger, index=True)
    last_used_ts: Mapped[int] = mapped_column(BigInteger, default=0)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    embed_id: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class Episode(Base):
    """Episodic memory: a remembered event."""
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    when_ts: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(256))
    summary: Mapped[str] = mapped_column(Text)
    emotion: Mapped[str | None] = mapped_column(String(32))
    intensity: Mapped[float] = mapped_column(Float, default=0.5)
    embed_id: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class Opinion(Base):
    """Opinion of the persona about a target."""
    __tablename__ = "opinions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_kind: Mapped[str] = mapped_column(String(16), index=True)
    target_id: Mapped[int] = mapped_column(BigInteger, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_ts: Mapped[int] = mapped_column(BigInteger, index=True)

    __table_args__ = (
        UniqueConstraint("target_kind", "target_id", name="uq_opinion_target"),
    )


class Feeling(Base):
    """Feeling toward a target, decays over time."""
    __tablename__ = "feelings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_kind: Mapped[str] = mapped_column(String(16), index=True)
    target_id: Mapped[int] = mapped_column(BigInteger, index=True)
    emotion: Mapped[str] = mapped_column(String(32), index=True)
    intensity: Mapped[float] = mapped_column(Float, default=0.5)
    decay_rate: Mapped[float] = mapped_column(Float, default=0.05)
    reason: Mapped[str | None] = mapped_column(Text)
    started_ts: Mapped[int] = mapped_column(BigInteger)
    updated_ts: Mapped[int] = mapped_column(BigInteger, index=True)

    __table_args__ = (
        Index("ix_feeling_target", "target_kind", "target_id"),
    )


class Relationship(Base):
    """Observed relation between two peers."""
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    a_id: Mapped[int] = mapped_column(BigInteger, index=True)
    b_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    strength: Mapped[float] = mapped_column(Float, default=0.5)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_ts: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        UniqueConstraint("a_id", "b_id", "chat_id", name="uq_relation"),
    )


class MoodState(Base):
    """Single-row mood snapshot."""
    __tablename__ = "mood_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    valence: Mapped[float] = mapped_column(Float, default=0.0)
    arousal: Mapped[float] = mapped_column(Float, default=0.3)
    energy: Mapped[float] = mapped_column(Float, default=0.7)
    focus: Mapped[float] = mapped_column(Float, default=0.5)
    stress: Mapped[float] = mapped_column(Float, default=0.2)
    fatigue: Mapped[float] = mapped_column(Float, default=0.2)
    note: Mapped[str | None] = mapped_column(Text)
    updated_ts: Mapped[int] = mapped_column(BigInteger)


class PresenceLog(Base):
    """Presence transitions over time."""
    __tablename__ = "presence_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    until_ts: Mapped[int | None] = mapped_column(BigInteger)
    started_ts: Mapped[int] = mapped_column(BigInteger, index=True)


class Sticker(Base):
    """A sticker the persona has seen or owns."""
    __tablename__ = "stickers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    file_unique_id: Mapped[str | None] = mapped_column(String(128), index=True)
    set_name: Mapped[str | None] = mapped_column(String(128), index=True)
    emoji: Mapped[str | None] = mapped_column(String(32))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    mood_valence: Mapped[float] = mapped_column(Float, default=0.0)
    mood_arousal: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str | None] = mapped_column(Text)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_ts: Mapped[int] = mapped_column(BigInteger, default=0)
    fits_persona: Mapped[float] = mapped_column(Float, default=0.5)
    local_path: Mapped[str | None] = mapped_column(String(256))


class GifMedia(Base):
    """A GIF the persona has seen or owns."""
    __tablename__ = "gifs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    file_unique_id: Mapped[str | None] = mapped_column(String(128), index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str | None] = mapped_column(Text)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_ts: Mapped[int] = mapped_column(BigInteger, default=0)
    fits_persona: Mapped[float] = mapped_column(Float, default=0.5)
    local_path: Mapped[str | None] = mapped_column(String(256))


class AttentionLog(Base):
    """Audit of attention cycles."""
    __tablename__ = "attention_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    started_ts: Mapped[int] = mapped_column(BigInteger, index=True)
    ended_ts: Mapped[int | None] = mapped_column(BigInteger)
    msgs_read: Mapped[int] = mapped_column(Integer, default=0)
    decided: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)


class JournalEntry(Base):
    """First-person inner journal entry."""
    __tablename__ = "journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    text: Mapped[str] = mapped_column(Text)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class KV(Base):
    """Generic key/value scratch store."""
    __tablename__ = "kv"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_ts: Mapped[int] = mapped_column(BigInteger)
