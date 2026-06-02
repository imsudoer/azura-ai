"""Pydantic v2 schema of the persona JSON."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from azura.constants import PERSONALITY_TRAITS


class Identity(BaseModel):
    """Basic identity."""
    model_config = ConfigDict(extra="ignore")

    name: str
    age: int = Field(ge=14, le=80)
    gender: Literal["f", "m", "nb"]
    city: str
    country: str
    timezone: str
    occupation: str
    education: str | None = None
    languages: list[str] = Field(default_factory=lambda: ["ru"])


class SpeechStyle(BaseModel):
    """How the persona writes."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    speech_register: Literal["formal", "neutral", "casual", "slangy"] = Field(default="casual", alias="register")
    sentence_length_avg: int = Field(default=8, ge=2, le=40)
    uses_emoji: Literal["never", "rare", "moderate", "often"] = "rare"
    emoji_palette: list[str] = Field(default_factory=list)
    uses_caps: Literal["never", "rare", "moderate", "often"] = "rare"
    punctuation: Literal["strict", "loose", "messy"] = "loose"
    typos_rate: float = Field(default=0.03, ge=0.0, le=0.2)
    favorite_words: list[str] = Field(default_factory=list)
    avoid_words: list[str] = Field(default_factory=list)
    catchphrases: list[str] = Field(default_factory=list)
    multi_message_chance: float = Field(default=0.35, ge=0.0, le=1.0)
    self_correction_chance: float = Field(default=0.12, ge=0.0, le=1.0)


class DailyRhythm(BaseModel):
    """Sleep / work schedule, local to persona timezone."""
    model_config = ConfigDict(extra="ignore")

    wake: str = "09:00"
    sleep: str = "00:30"
    work_blocks: list[tuple[str, str]] = Field(default_factory=list)
    nap_chance: float = Field(default=0.05, ge=0.0, le=1.0)
    night_owl: bool = False
    weekend_shift_minutes: int = 90


class SocialBehavior(BaseModel):
    """Tendencies of social engagement."""
    model_config = ConfigDict(extra="ignore")

    first_message_per_hour: float = Field(default=0.06, ge=0.0, le=1.0)
    reply_speed: Literal["instant", "fast", "medium", "slow", "lazy"] = "medium"
    ghost_chance: float = Field(default=0.05, ge=0.0, le=1.0)
    read_no_reply_chance: float = Field(default=0.2, ge=0.0, le=1.0)
    initiate_close_chance: float = Field(default=0.4, ge=0.0, le=1.0)
    crowd_attention_span_min: int = Field(default=20, ge=1, le=720)


class Household(BaseModel):
    """Living arrangement and family context."""
    model_config = ConfigDict(extra="ignore")

    lives_with: list[str] = Field(default_factory=list)
    family: list[dict] = Field(default_factory=list)
    pets: list[str] = Field(default_factory=list)
    home_notes: str | None = None


class SocialCircle(BaseModel):
    """Imaginary social graph (named people not on Telegram)."""
    model_config = ConfigDict(extra="ignore")

    close_friends: list[dict] = Field(default_factory=list)
    acquaintances: list[dict] = Field(default_factory=list)
    rivals: list[dict] = Field(default_factory=list)
    romantic: dict | None = None


class LifeEvent(BaseModel):
    """A past event shaping the persona."""
    model_config = ConfigDict(extra="ignore")

    when: str
    title: str
    description: str
    impact: str | None = None


class CurrentLifeArc(BaseModel):
    """Ongoing storyline of the persona right now."""
    model_config = ConfigDict(extra="ignore")

    headline: str
    goals_short: list[str] = Field(default_factory=list)
    goals_long: list[str] = Field(default_factory=list)
    worries: list[str] = Field(default_factory=list)
    recent_changes: list[str] = Field(default_factory=list)


class Boundaries(BaseModel):
    """Behavioural limits."""
    model_config = ConfigDict(extra="ignore")

    will_not_discuss: list[str] = Field(default_factory=list)
    soft_topics: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    never_admit_ai: bool = True


class Persona(BaseModel):
    """Full immutable persona snapshot."""
    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1
    seed: int = 0

    identity: Identity
    appearance_self_image: str
    background: str
    values: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)

    traits: dict[str, float]
    derived: dict[str, str] = Field(default_factory=dict)

    speech: SpeechStyle = Field(default_factory=SpeechStyle)
    rhythm: DailyRhythm = Field(default_factory=DailyRhythm)
    social: SocialBehavior = Field(default_factory=SocialBehavior)

    household: Household = Field(default_factory=Household)
    social_circle: SocialCircle = Field(default_factory=SocialCircle)
    life_events: list[LifeEvent] = Field(default_factory=list)
    arc: CurrentLifeArc

    boundaries: Boundaries = Field(default_factory=Boundaries)
    habits: list[str] = Field(default_factory=list)
    tastes: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("traits")
    @classmethod
    def _check_traits(cls, v: dict[str, float]) -> dict[str, float]:
        """Ensure every known trait is present and clamped."""
        out: dict[str, float] = {}
        for k in PERSONALITY_TRAITS:
            x = float(v.get(k, 0.5))
            out[k] = max(0.0, min(1.0, x))
        return out
