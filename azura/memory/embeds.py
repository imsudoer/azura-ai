"""Embedding cache: batches text -> vector calls, dedups within a session."""
from __future__ import annotations

from azura.llm.router import embed_texts


class EmbedCache:
    """Tiny in-memory cache so we don't re-embed the same string twice in a tick."""

    def __init__(self) -> None:
        self._cache: dict[str, list[float]] = {}

    async def get(self, text: str) -> list[float]:
        v = self._cache.get(text)
        if v is not None:
            return v
        out = await embed_texts([text])
        v = out[0]
        self._cache[text] = v
        return v

    async def get_many(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if t not in self._cache]
        if missing:
            vecs = await embed_texts(missing)
            for t, v in zip(missing, vecs, strict=True):
                self._cache[t] = v
        return [self._cache[t] for t in texts]

    def clear(self) -> None:
        self._cache.clear()
