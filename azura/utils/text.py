"""Text helpers: tokenization, length stats, sanitization."""
from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+")
_MENTION_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]{3,31})")


def normalize(s: str) -> str:
    """NFC unicode + trim + collapse whitespace."""
    s = unicodedata.normalize("NFC", s)
    return _WS_RE.sub(" ", s).strip()


def words(s: str) -> list[str]:
    """Extract word tokens."""
    return _WORD_RE.findall(s.lower())


def word_count(s: str) -> int:
    return len(words(s))


def is_short(s: str, threshold: int = 4) -> bool:
    """Whether a message is short enough to look casual."""
    return word_count(s) <= threshold


def strip_urls(s: str) -> str:
    return _URL_RE.sub("", s)


def find_mentions(s: str) -> list[str]:
    """Extract @usernames without the '@'."""
    return _MENTION_RE.findall(s or "")


def contains_name(s: str, names: list[str]) -> bool:
    """Case-insensitive substring check across multiple name variants."""
    if not s or not names:
        return False
    low = s.lower()
    return any(n.lower() in low for n in names if n)


def truncate(s: str, n: int) -> str:
    """Hard truncate keeping a unicode ellipsis when cut."""
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def split_sentences(s: str) -> list[str]:
    """Cheap sentence splitter for ru/en chat text."""
    parts = re.split(r"(?<=[.!?…])\s+", s.strip())
    return [p for p in parts if p]


def ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    """Build n-grams from a token list."""
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]
