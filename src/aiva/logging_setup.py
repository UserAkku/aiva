"""Pretty console logs + a rotating file in ``data/logs``."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger


class _InterceptHandler(logging.Handler):
    """Route stdlib logging (uvicorn, httpx…) through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(data_dir: Path, level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> <level>{level: <7}</level> <cyan>{name}</cyan> {message}",
    )
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    logger.add(data_dir / "logs" / "aiva.log", level="DEBUG", rotation="5 MB", retention=5, enqueue=True)
    logging.basicConfig(handlers=[_InterceptHandler()], level=logging.INFO, force=True)
    for noisy in (
        "httpx",
        "httpcore",
        "httpx2",
        "httpcore2",
        "websockets",
        "uvicorn.access",
        "mcp",
        "fastmcp",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)
