"""Avoid repeating recent phrasings — n-gram overlap penalty over a rolling window."""
from __future__ import annotations

from collections import deque

from azura.utils.text import ngrams, words


class StyleDiversity:
    """Track recent self messages and detect heavy n-gram overlap, per-chat."""

    def __init__(self, *, window: int = 30, n: int = 3) -> None:
        self.window = window
        self.n = n
        self._global: deque[tuple[str, set[tuple[str, ...]]]] = deque(maxlen=window)
        self._per_chat: dict[int, deque[tuple[str, set[tuple[str, ...]]]]] = {}

    def _bucket(self, chat_id: int | None) -> deque[tuple[str, set[tuple[str, ...]]]]:
        if chat_id is None:
            return self._global
        bq = self._per_chat.get(chat_id)
        if bq is None:
            bq = deque(maxlen=self.window)
            self._per_chat[chat_id] = bq
        return bq

    def add(self, text: str, chat_id: int | None = None) -> None:
        toks = words(text)
        grams = set(ngrams(toks, self.n))
        item = (text, grams)
        self._global.append(item)
        if chat_id is not None:
            self._bucket(chat_id).append(item)

    def overlap_ratio(self, text: str, chat_id: int | None = None) -> float:
        toks = words(text)
        grams = set(ngrams(toks, self.n))
        if not grams:
            return 0.0
        sources = [self._global]
        if chat_id is not None:
            sources.append(self._bucket(chat_id))
        best = 0.0
        for src in sources:
            for _, past in src:
                if not past:
                    continue
                inter = grams & past
                ratio = len(inter) / max(1, len(grams))
                if ratio > best:
                    best = ratio
        return best

    def too_similar(
        self, text: str, chat_id: int | None = None, threshold: float = 0.35
    ) -> bool:
        return self.overlap_ratio(text, chat_id) >= threshold

    def recent_texts(self, chat_id: int | None = None, limit: int = 6) -> list[str]:
        src = self._bucket(chat_id) if chat_id is not None else self._global
        out = [t for t, _ in list(src)[-limit:]]
        return out
