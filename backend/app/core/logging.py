"""
Basic structured-ish logging setup.

We keep this intentionally simple in Phase 0: stdlib logging configured with
a consistent format. This can be swapped for structlog/JSON logging later
without touching call sites, since everything goes through get_logger().
"""

import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
