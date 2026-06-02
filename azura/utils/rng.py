"""Deterministic seeded RNG with probability helpers."""
from __future__ import annotations

import hashlib
import os
import random
from typing import Iterable, Sequence, TypeVar

T = TypeVar("T")


class Rng:
    """Thin wrapper over random.Random with convenience helpers."""

    def __init__(self, seed: int | None = None) -> None:
        if seed is None:
            seed = int.from_bytes(os.urandom(8), "little")
        self.seed = seed
        self._r = random.Random(seed)

    def chance(self, p: float) -> bool:
        """Return True with probability p (clamped to [0, 1])."""
        if p <= 0:
            return False
        if p >= 1:
            return True
        return self._r.random() < p

    def uniform(self, a: float, b: float) -> float:
        return self._r.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        return self._r.randint(a, b)

    def gauss(self, mu: float, sigma: float) -> float:
        return self._r.gauss(mu, sigma)

    def choice(self, seq: Sequence[T]) -> T:
        return self._r.choice(seq)

    def choices(self, seq: Sequence[T], k: int = 1, weights: Sequence[float] | None = None) -> list[T]:
        return self._r.choices(seq, weights=weights, k=k)

    def shuffle(self, seq: list[T]) -> None:
        self._r.shuffle(seq)

    def sample(self, seq: Iterable[T], k: int) -> list[T]:
        return self._r.sample(list(seq), k)

    def jitter(self, base: float, pct: float = 0.2) -> float:
        """Return base ± pct of base, clamped to be non-negative."""
        d = base * pct
        return max(0.0, base + self._r.uniform(-d, d))

    def child(self, salt: str) -> "Rng":
        """Derive a deterministic child RNG for a subsystem."""
        h = hashlib.blake2b(f"{self.seed}:{salt}".encode(), digest_size=8).digest()
        return Rng(int.from_bytes(h, "little"))


def stable_hash(value: str) -> int:
    """Stable 64-bit hash of a string."""
    h = hashlib.blake2b(value.encode(), digest_size=8).digest()
    return int.from_bytes(h, "little", signed=False)
