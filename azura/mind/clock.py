"""Persona-local clock: time of day, day phase, weekend awareness."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from azura.personality.schema import Persona
from azura.utils.timez import in_window, now_in, parse_hhmm

DayPhase = Literal["deep_night", "early_morning", "morning", "day", "afternoon", "evening", "late_evening", "night"]


@dataclass
class ClockSnapshot:
    """Frozen view of the persona's local time."""
    local: datetime
    phase: DayPhase
    is_weekend: bool
    is_sleep_window: bool
    is_work_window: bool


def snapshot(persona: Persona, *, now: datetime | None = None) -> ClockSnapshot:
    """Compute a clock snapshot in the persona's timezone."""
    tz = persona.identity.timezone
    local = now or now_in(tz)
    phase = _phase(local)
    weekend = local.weekday() >= 5
    sleep = in_window(local, persona.rhythm.wake, persona.rhythm.sleep) is False
    work = any(in_window(local, s, e) for s, e in persona.rhythm.work_blocks)
    return ClockSnapshot(local=local, phase=phase, is_weekend=weekend, is_sleep_window=sleep, is_work_window=work)


def _phase(local: datetime) -> DayPhase:
    h = local.hour
    if h < 4:
        return "deep_night"
    if h < 7:
        return "early_morning"
    if h < 10:
        return "morning"
    if h < 13:
        return "day"
    if h < 17:
        return "afternoon"
    if h < 21:
        return "evening"
    if h < 24:
        return "late_evening"
    return "night"


def seconds_until_wake(persona: Persona, local: datetime) -> int:
    """Seconds until the next wake time."""
    t = parse_hhmm(persona.rhythm.wake)
    target = local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if target <= local:
        from datetime import timedelta
        target += timedelta(days=1)
    return int((target - local).total_seconds())
