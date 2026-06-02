"""ToolRegistry: pick a context-relevant subset of tools for each agent call."""
from __future__ import annotations

from typing import Awaitable, Callable

from azura.mind.agent import ToolSpec


class ToolRegistry:
    """Holds named tool specs plus tags for situation-aware selection."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._tags: dict[str, set[str]] = {}

    def add(self, spec: ToolSpec, *tags: str) -> None:
        self._tools[spec.name] = spec
        self._tags[spec.name] = set(tags)

    def remove(self, name: str) -> None:
        self._tools.pop(name, None)
        self._tags.pop(name, None)

    def names(self) -> list[str]:
        return list(self._tools)

    def select(self, *, include_tags: set[str] | None = None, exclude_tags: set[str] | None = None) -> list[ToolSpec]:
        inc = include_tags or set()
        exc = exclude_tags or set()
        out: list[ToolSpec] = []
        for n, t in self._tools.items():
            tags = self._tags[n]
            if inc and not (tags & inc):
                continue
            if exc and (tags & exc):
                continue
            out.append(t)
        return out


def make_spec(
    name: str,
    description: str,
    parameters: dict,
    fn: Callable[[dict], Awaitable],
) -> ToolSpec:
    """Tiny ToolSpec helper used by every family module."""
    return ToolSpec(name=name, description=description, parameters=parameters, fn=fn)
