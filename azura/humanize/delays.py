"""Compute realistic delays before reading/typing/sending."""
from __future__ import annotations

from dataclasses import dataclass

from azura.config import get_settings
from azura.mind.clock import ClockSnapshot
from azura.mind.mood import MoodView
from azura.personality.schema import Persona
from azura.utils.rng import Rng


@dataclass
class DelayPlan:
    """Plan of delays around producing one reply burst."""
    pre_read_s: float
    pre_type_s: float
    type_burst_s: float
    after_send_s: float


_REPLY_SPEED_MUL = {
    "instant": 0.5,
    "fast": 0.75,
    "medium": 1.0,
    "slow": 1.6,
    "lazy": 2.4,
}


def reply_delay(
    *,
    persona: Persona,
    mood: MoodView,
    clock: ClockSnapshot,
    rng: Rng,
    text_len: int,
    urgency: float = 0.0,
    in_private: bool = True,
) -> DelayPlan:
    """Estimate human-shaped pre-read, pre-type, typing burst and after-send delays."""
    s = get_settings()
    mul = _REPLY_SPEED_MUL.get(persona.social.reply_speed, 1.0)
    t = persona.traits
    base_pre = rng.uniform(2.0, 9.0)
    base_pre *= mul
    base_pre *= 1.0 + (1 - t.get("attention_span", 0.5)) * 0.5
    base_pre *= 1.0 + mood.fatigue * 0.8
    base_pre *= 1.0 - urgency * 0.7
    if clock.phase in ("deep_night", "night"):
        base_pre *= 1.8
    if clock.phase in ("early_morning",):
        base_pre *= 1.4
    if clock.is_work_window:
        base_pre *= 1.3
    if not in_private:
        base_pre *= 1.3
    base_pre = max(s.humanize_min_reply_delay_s, min(s.humanize_max_reply_delay_s, base_pre))

    pre_type = rng.uniform(0.4, 1.6) * mul

    cps = 3.5 + t.get("conscientiousness", 0.5) * 1.5 - mood.fatigue * 1.0
    cps = max(1.5, cps)
    type_burst = max(0.8, text_len / cps + rng.uniform(-0.8, 1.2))
    type_burst *= mul

    after = rng.uniform(0.6, 2.4)
    return DelayPlan(
        pre_read_s=round(base_pre, 2),
        pre_type_s=round(pre_type, 2),
        type_burst_s=round(type_burst, 2),
        after_send_s=round(after, 2),
    )


def split_burst_delays(rng: Rng, n_messages: int) -> list[float]:
    """Mini delays between messages in a multi-message burst."""
    return [round(rng.uniform(0.8, 2.4), 2) for _ in range(max(0, n_messages - 1))]
