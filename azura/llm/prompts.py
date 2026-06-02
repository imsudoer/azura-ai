"""Jinja2 loader for prompt templates under llm/templates/."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATES_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2", "txt", "md")),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
        enable_async=False,
        keep_trailing_newline=False,
    )


def render(name: str, **ctx) -> str:
    """Render a template by file name (e.g. 'persona_outline.j2')."""
    tpl = _env().get_template(name)
    return tpl.render(**ctx)


def has_template(name: str) -> bool:
    return (TEMPLATES_DIR / name).exists()
