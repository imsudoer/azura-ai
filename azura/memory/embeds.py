"""Embedding cache: batches text -> vector calls, dedups within a session.

If `EMBEDDINGS_ENABLED=false` in env, every call short-circuits to None so
that callers (which already handle None gracefully) skip vec storage entirely.
"""
from __future__ import annotations

from azura.config import get_settings
from azura.llm.router import embed_texts
from azura.utils.log import get_logger

log = get_logger("memory.embeds")


class EmbedCache:
    """Tiny in-memory cache so we don't re-embed the same string twice in a tick."""

    def __init__(self) -> None:
        self._cache: dict[str, list[float]] = {}
        self._disabled: bool = not get_settings().embeddings_enabled

    async def get(self, text: str) -> list[float] | None:
        """Return embedding for one text, or None if embeddings are off / failed."""
        if self._disabled or not text:
            return None
        v = self._cache.get(text)
        if v is not None:
            return v
        try:
            out = await embed_texts([text])
        except Exception as e:
            log.warning("embed failed (one-off, not disabling): {}", e)
            return None
        if not out:
            return None
        v = out[0]
        self._cache[text] = v
        return v

    async def get_many(self, texts: list[str]) -> list[list[float] | None]:
        """Batch-embed; entries become None if disabled / failed."""
        if self._disabled:
            return [None] * len(texts)
        missing = [t for t in texts if t and t not in self._cache]
        if missing:
            try:
                vecs = await embed_texts(missing)
            except Exception as e:
                log.warning("embed batch failed (one-off, not disabling): {}", e)
                return [self._cache.get(t) for t in texts]
            for t, v in zip(missing, vecs, strict=True):
                self._cache[t] = v
        return [self._cache.get(t) for t in texts]

    def clear(self) -> None:
        self._cache.clear()

    @property
    def enabled(self) -> bool:
        return not self._disabled
