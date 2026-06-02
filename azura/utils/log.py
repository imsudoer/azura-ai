"""Logging via loguru with rotating file sink."""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

from loguru import logger

_inited = False


def _suppress_noisy_warnings() -> None:
    """Silence kurigram/pyrogram deprecations and other library noise."""
    import logging
    for needle in (
        "message.forward_from",
        "message.forward_from_chat",
        "message.forward_signature",
        "message.forward_sender_name",
        "message.forward_date",
    ):
        warnings.filterwarnings("ignore", message=f".*{needle}.*")
    import logging as _logging
    class _DropDeprecations(_logging.Filter):
        def filter(self, record: _logging.LogRecord) -> bool:
            m = record.getMessage()
            if "deprecated" in m or "forward_from" in m or "forward_origin" in m:
                return False
            return True
    root = _logging.getLogger()
    root.addFilter(_DropDeprecations())
    for name in (
        "pyrogram", "pyrogram.session", "pyrogram.connection",
        "pyrogram.dispatcher", "pyrogram.client", "pyrogram.types",
        "pyrogram.types.messages_and_media.message",
    ):
        lg = _logging.getLogger(name)
        lg.setLevel(_logging.ERROR)
        lg.addFilter(_DropDeprecations())
        lg.propagate = False


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> None:
    """Configure stderr sink with colors and an optional rotating file sink."""
    global _inited
    if _inited:
        return
    _suppress_noisy_warnings()
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=False,
        format=(
            "<green>{time:HH:mm:ss}</green> "
            "<level>{level: <8}</level> "
            "<cyan>{name}:{line}</cyan> | <level>{message}</level>"
        ),
    )
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "azura.log",
            level=level,
            rotation="20 MB",
            retention=10,
            compression="zip",
            enqueue=True,
            backtrace=True,
            diagnose=False,
        )
    _inited = True


def get_logger(name: str):
    """Return a logger bound with a scope name."""
    return logger.bind(scope=name)
