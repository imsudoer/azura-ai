"""Logging via loguru with rotating file sink."""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_inited = False


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> None:
    """Configure stderr sink with colors and an optional rotating file sink."""
    global _inited
    if _inited:
        return
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
