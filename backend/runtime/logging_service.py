"""Best-effort bounded application logging for the desktop product."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import platform
import sys

from .identity import BUILD_CHANNEL, PRODUCT_NAME, VERSION, build_identity
from .paths import runtime_paths

LOGGER_NAME = "quantumstudio"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3


def configure_logging(*, environ=None, home=None, platform_name=None) -> logging.Logger:
    """Configure logging without allowing an unwritable log root to block startup."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if any(getattr(handler, "_quantumstudio", False) for handler in logger.handlers):
        return logger
    try:
        log_dir = runtime_paths(environ=environ, home=home, platform_name=platform_name).logs
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_dir / "quantumstudio.log", maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
        handler._quantumstudio = True
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    except (OSError, TypeError, ValueError):
        # A logging failure must never recursively prevent the GUI from opening.
        fallback = logging.NullHandler()
        fallback._quantumstudio = True
        logger.addHandler(fallback)
    logger.info("Session started product=%s version=%s channel=%s build=%s os=%s python=%s", PRODUCT_NAME, VERSION, BUILD_CHANNEL, build_identity().get("commit", "unknown"), platform.platform(), sys.version.split()[0])
    return logger
