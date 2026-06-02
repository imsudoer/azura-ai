"""Time, timezone and day-window helpers."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo


def now_utc() -> datetime:
    """Aware current time in UTC."""
    return datetime.now(timezone.utc)


def now_in(tz_name: str) -> datetime:
    """Aware current time in the given timezone."""
    return datetime.now(ZoneInfo(tz_name))


def to_local(dt: datetime, tz_name: str) -> datetime:
    """Convert datetime to the given timezone, assuming UTC when naive."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz_name))


def ts() -> int:
    """Unix timestamp, seconds."""
    return int(now_utc().timestamp())


def parse_hhmm(s: str) -> time:
    """Parse "HH:MM" into a time object."""
    h, m = s.split(":")
    return time(int(h), int(m))


def in_window(local_dt: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    """Whether the time-of-day of local_dt is inside [start, end], wrapping over midnight."""
    s = parse_hhmm(start_hhmm)
    e = parse_hhmm(end_hhmm)
    cur = local_dt.time()
    if s <= e:
        return s <= cur <= e
    return cur >= s or cur <= e


def seconds_until(local_dt: datetime, target_hhmm: str) -> int:
    """Seconds remaining until the next occurrence of target_hhmm."""
    t = parse_hhmm(target_hhmm)
    today_target = local_dt.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if today_target <= local_dt:
        today_target += timedelta(days=1)
    return int((today_target - local_dt).total_seconds())


def tz_of(name: str) -> tzinfo:
    """Resolve tzinfo by IANA name."""
    return ZoneInfo(name)
