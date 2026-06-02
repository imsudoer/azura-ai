"""Avoid repeating recent phrasings — n-gram overlap penalty over a rolling window."""
from __future__ import annotations

from collections import deque

from azura.utils.text import ngrams, words


class StyleDiversity:
    """Track recent self messages and detect heavy n-gram overlap."""

    def __init__(self, *, window: int = 50, n: int = 4) -> None:
        self.window = window
        self.n = n
        self._recent: deque[tuple[str, set[tuple[str, ...]]]] = deque(maxlen=window)

    def add(self, text: str) -> None:
        toks = words(text)
        grams = set(ngrams(toks, self.n))
        self._recent.append((text, grams))

    def overlap_ratio(self, text: str) -> float:
        """Max share of n-grams in candidate that already appeared in window."""
        toks = words(text)
        grams = set(ngrams(toks, self.n))
        if not grams:
            return 0.0
        best = 0.0
        for _, past in self._recent:
            if not past:
                continue
            inter = grams & past
            ratio = len(inter) / max(1, len(grams))
            if ratio > best:
                best = ratio
        return best

    def too_similar(self, text: str, threshold: float = 0.45) -> bool:
        return self.overlap_ratio(text) >= threshold
