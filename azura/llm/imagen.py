"""OnlySq Imagen client: generate a photograph and save to disk.

Calls the OpenAI-compatible image endpoint with `model = MODEL_IMAGEN`.
Returns the bytes plus the path written into data/media_cache/portraits/.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from azura.config import get_settings
from azura.llm.client import get_client
from azura.utils.log import get_logger
from azura.utils.timez import ts

log = get_logger("llm.imagen")


def _portraits_dir() -> Path:
    s = get_settings()
    p = s.media_cache_dir / "portraits"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def generate(
    *,
    prompt: str,
    size: str = "1024x1024",
    n: int = 1,
) -> list[Path]:
    """Call the OnlySq image endpoint; save each result to portraits/ and return paths."""
    s = get_settings()
    if not s.onlysq_api_key:
        raise RuntimeError("ONLYSQ_API_KEY missing")
    cli = get_client()
    log.info("imagen request model={} size={} n={}", s.model_imagen, size, n)
    try:
        resp = await cli.images.generate(
            model=s.model_imagen,
            prompt=prompt,
            size=size,
            n=n,
        )
    except Exception as e:
        log.warning("imagen call failed: {}", e)
        raise

    out_paths: list[Path] = []
    for i, item in enumerate(getattr(resp, "data", []) or []):
        data: bytes | None = None
        b64 = getattr(item, "b64_json", None)
        if b64:
            data = base64.b64decode(b64)
        else:
            url = getattr(item, "url", None)
            if url:
                import httpx
                async with httpx.AsyncClient(timeout=60) as h:
                    r = await h.get(url)
                    r.raise_for_status()
                    data = r.content
        if not data:
            continue
        path = _portraits_dir() / f"portrait_{ts()}_{i}.png"
        path.write_bytes(data)
        out_paths.append(path)
    log.info("imagen generated {} images", len(out_paths))
    return out_paths
