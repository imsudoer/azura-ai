"""Vision describer: turn a local image/video frame into a short text description.

Backed by an OpenAI-compatible vision-capable model (configured via MODEL_VISION).
Falls back to None silently if disabled or the model errors.
"""
from __future__ import annotations

import base64
from pathlib import Path

from azura.config import get_settings
from azura.llm.client import chat_text
from azura.utils.log import get_logger

log = get_logger("llm.vision")


_SYS = (
    "You describe images and short clips as a third-party observer in 1-2 short sentences. "
    "Be concrete: what is shown, colors, mood, text in the image. No moral judgments, "
    "no AI disclaimers. Plain prose, no markdown, no bullets."
)


def _b64_data_url(path: Path) -> str | None:
    """Encode a file as data: URL for OpenAI image_url content."""
    try:
        b = path.read_bytes()
    except OSError:
        return None
    suffix = path.suffix.lower().lstrip(".")
    mime = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "webp": "image/webp", "gif": "image/gif",
    }.get(suffix, "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(b).decode('ascii')}"


async def describe_image(path: Path, *, hint: str | None = None) -> str | None:
    """Describe an image at `path`. Returns text or None on failure / disabled."""
    s = get_settings()
    if not s.vision_enabled or not s.model_vision:
        return None
    url = _b64_data_url(path)
    if url is None:
        return None
    user_content = [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": hint or "describe this image briefly."},
    ]
    try:
        out = await chat_text(
            model=s.model_vision,
            messages=[
                {"role": "system", "content": _SYS},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=180,
        )
        return out.strip() or None
    except Exception as e:
        log.warning("vision failed for {}: {}", path.name, e)
        return None
