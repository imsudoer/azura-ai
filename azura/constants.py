"""Global immutable constants and enums."""
from __future__ import annotations

from enum import Enum


class ChatKind(str, Enum):
    """Telegram chat type."""
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"
    BOT = "bot"


class Presence(str, Enum):
    """Presence states of the persona."""
    ASLEEP = "asleep"
    OFFLINE = "offline"
    AFK = "afk"
    ONLINE = "online"
    BUSY = "busy"


class MemoryKind(str, Enum):
    """Memory tiers."""
    SHORT = "short"
    LONG = "long"
    EPISODIC = "episodic"
    GLOBAL = "global"
    DAILY = "daily"


class Proximity(str, Enum):
    """Social proximity tier toward a peer."""
    STRANGER = "stranger"
    ACQUAINTANCE = "acquaintance"
    FRIEND = "friend"
    CLOSE = "close"


class OpinionTarget(str, Enum):
    """What an opinion is about."""
    USER = "user"
    CHAT = "chat"
    TOPIC = "topic"


class FeelingTarget(str, Enum):
    """What a feeling is directed at."""
    USER = "user"
    CHAT = "chat"


PROXIMITY_THRESHOLDS: dict[Proximity, tuple[int, float]] = {
    Proximity.STRANGER: (0, 0.0),
    Proximity.ACQUAINTANCE: (10, 7 * 24 * 3600),
    Proximity.FRIEND: (40, 30 * 24 * 3600),
    Proximity.CLOSE: (80, 90 * 24 * 3600),
}

ATTENTION_ORDER: tuple[str, ...] = (
    "private",
    "group",
    "channel",
    "private_muted",
    "group_muted",
)

PERSONALITY_TRAITS: tuple[str, ...] = (
    "empathy", "narcissism", "dominance", "aggression", "adaptiveness",
    "provocativeness", "supportiveness", "sarcasm", "honesty", "jealousy",
    "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism",
    "talkativeness", "attention_span", "patience", "curiosity", "romanticism",
    "pettiness", "grudge_holding", "forgiveness_speed", "social_battery",
    "playfulness", "secrecy", "loyalty", "impulsivity",
)
