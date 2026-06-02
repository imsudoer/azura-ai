"""Factories for tests: synthetic personas, RNG, persona dump helpers."""
from __future__ import annotations

from typing import Any

from azura.constants import PERSONALITY_TRAITS
from azura.personality.schema import Persona


def make_persona(**overrides) -> Persona:
    """Build a fully-validated synthetic Persona with safe defaults."""
    traits = {k: 0.5 for k in PERSONALITY_TRAITS}
    traits.update(overrides.pop("traits", {}))
    base: dict[str, Any] = {
        "schema_version": 1,
        "seed": 1,
        "identity": {
            "name": "Mira",
            "age": 23,
            "gender": "f",
            "city": "Prague",
            "country": "Czechia",
            "timezone": "Europe/Prague",
            "occupation": "junior dev",
            "languages": ["ru", "en"],
        },
        "appearance_self_image": "tired but cute",
        "background": "she grew up in Brno, moved to Prague at 19",
        "values": ["honesty", "curiosity"],
        "interests": ["indie music", "react", "cats"],
        "dislikes": ["small talk"],
        "secrets": [],
        "traits": traits,
        "speech": {
            "register": "casual",
            "sentence_length_avg": 8,
            "uses_emoji": "rare",
            "emoji_palette": ["🙃"],
            "uses_caps": "rare",
            "punctuation": "loose",
            "typos_rate": 0.04,
            "favorite_words": ["короче"],
            "avoid_words": ["зайка"],
            "catchphrases": ["ну и вот"],
            "multi_message_chance": 0.4,
            "self_correction_chance": 0.15,
        },
        "rhythm": {
            "wake": "09:30",
            "sleep": "01:00",
            "work_blocks": [["10:30", "19:00"]],
            "nap_chance": 0.06,
            "night_owl": True,
            "weekend_shift_minutes": 90,
        },
        "social": {
            "first_message_per_hour": 0.08,
            "reply_speed": "medium",
            "ghost_chance": 0.05,
            "read_no_reply_chance": 0.2,
            "initiate_close_chance": 0.4,
            "crowd_attention_span_min": 25,
        },
        "household": {
            "lives_with": ["roommate"],
            "family": [],
            "pets": ["cat: Mocha"],
            "home_notes": None,
        },
        "social_circle": {"close_friends": [], "acquaintances": [], "rivals": []},
        "life_events": [],
        "arc": {
            "headline": "shipping a dashboard",
            "goals_short": ["ship MVP"],
            "goals_long": [],
            "worries": [],
            "recent_changes": [],
        },
        "boundaries": {
            "will_not_discuss": [],
            "soft_topics": [],
            "triggers": ["fake"],
            "never_admit_ai": True,
        },
        "habits": [],
        "tastes": {},
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    return Persona.model_validate(base)
