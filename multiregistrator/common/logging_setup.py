"""File logging for MultiRegistrator.

Errors that were previously swallowed silently (``except Exception: pass``)
are written to a real ``*.log`` file next to the program
(``<program>/logs/<component>.log``) so nothing is ever lost.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import app_root

LOGGER_NAME = "multiregistrator"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
MAX_BYTES = 2_000_000
BACKUP_COUNT = 5


def log_dir(base_dir: Optional[Path] = None) -> Path:
    """Directory where ``*.log`` files are stored."""

    root = Path(base_dir) if base_dir is not None else app_root()
    return root / "logs"


def setup_logging(
    component: str = "multiregistrator",
    base_dir: Optional[Path] = None,
    level: int = logging.INFO,
    console: bool = False,
) -> Path:
    """Attach a rotating ``<component>.log`` file handler and return its path."""

    directory = log_dir(base_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = (directory / f"{component}.log").resolve()

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    target = str(path)
    if not any(
        isinstance(handler, RotatingFileHandler)
        and getattr(handler, "baseFilename", None) == target
        for handler in logger.handlers
    ):
        file_handler = RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(file_handler)

    if console and sys.stderr is not None:
        has_stream = any(
            isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, RotatingFileHandler)
            for handler in logger.handlers
        )
        if not has_stream:
            stream_handler = logging.StreamHandler(sys.stderr)
            stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(stream_handler)

    return path


def get_logger(name: str) -> logging.Logger:
    """Return a child logger (messages go to the configured ``*.log`` file)."""

    return logging.getLogger(f"{LOGGER_NAME}.{name}")
