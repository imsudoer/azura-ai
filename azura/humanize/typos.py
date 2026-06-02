"""Insert realistic typos and optional follow-up corrections."""
from __future__ import annotations

import re

from azura.utils.rng import Rng

_NEIGHBORS = {
    "a": "qwsz", "b": "vghn", "c": "xdfv", "d": "serfcx", "e": "wrsdf",
    "f": "drtgvc", "g": "ftyhbv", "h": "gyujnb", "i": "ujko", "j": "huiknm",
    "k": "jilom", "l": "kop", "m": "njk", "n": "bhjm", "o": "iklp",
    "p": "ol", "q": "wa", "r": "etdf", "s": "awedxz", "t": "ryfg",
    "u": "yihj", "v": "cfgb", "w": "qase", "x": "zsdc", "y": "tuhg",
    "z": "asx",
    "а": "ыфявс", "б": "юьт", "в": "ыапр", "г": "нрп", "д": "лвж",
    "е": "куы", "ё": "е", "ж": "эдх", "з": "хщш", "и": "кмто",
    "й": "цф", "к": "цулй", "л": "ьжо", "м": "ис", "н": "ргп",
    "о": "иль", "п": "анг", "р": "оаи", "с": "чмы", "т": "ье",
    "у": "ецк", "ф": "ывй", "х": "зэж", "ц": "уйй", "ч": "ясь",
    "ш": "щгз", "щ": "шжз", "ъ": "хэ", "ы": "ваи", "ь": "трм",
    "э": "хж", "ю": "бь", "я": "чфы",
}
_TOK_RE = re.compile(r"\w+", re.UNICODE)


def _swap(s: str, i: int) -> str:
    if i < 0 or i + 1 >= len(s):
        return s
    return s[:i] + s[i + 1] + s[i] + s[i + 2:]


def _drop(s: str, i: int) -> str:
    if i < 0 or i >= len(s):
        return s
    return s[:i] + s[i + 1:]


def _double(s: str, i: int) -> str:
    if i < 0 or i >= len(s):
        return s
    return s[:i] + s[i] + s[i:]


def _replace_neighbor(s: str, i: int, rng: Rng) -> str:
    if i < 0 or i >= len(s):
        return s
    ch = s[i].lower()
    nb = _NEIGHBORS.get(ch)
    if not nb:
        return s
    r = rng.choice(nb)
    if s[i].isupper():
        r = r.upper()
    return s[:i] + r + s[i + 1:]


def inject_typos(text: str, *, rate: float, rng: Rng) -> tuple[str, list[tuple[str, str]]]:
    """Return (text_with_typos, [(original_word, typo_word)]).

    rate is per-word probability. We touch at most 1 character per word.
    """
    if rate <= 0 or not text:
        return text, []
    words = _TOK_RE.findall(text)
    if not words:
        return text, []
    typos: list[tuple[str, str]] = []
    out = text
    for w in words:
        if len(w) < 4 or not rng.chance(rate):
            continue
        i = rng.randint(1, max(1, len(w) - 2))
        op = rng.choice(("swap", "drop", "double", "neighbor"))
        if op == "swap":
            new = _swap(w, i)
        elif op == "drop":
            new = _drop(w, i)
        elif op == "double":
            new = _double(w, i)
        else:
            new = _replace_neighbor(w, i, rng)
        if new == w:
            continue
        out = re.sub(rf"\b{re.escape(w)}\b", new, out, count=1)
        typos.append((w, new))
    return out, typos


def correction_messages(typos: list[tuple[str, str]], *, rng: Rng, chance: float) -> list[str]:
    """Produce 'oops, *word' style follow-ups for some typos."""
    out: list[str] = []
    for orig, _ in typos:
        if rng.chance(chance):
            out.append(f"*{orig}")
    return out[:2]
