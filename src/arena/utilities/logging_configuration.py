"""Configurable logging: choose how much the application writes to its log.

Call :func:`configure_logging` once at start-up. Only the ``arena`` logger
is configured, so other libraries' logging is left alone.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

LOG_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class LogLevel(Enum):
    """How much to log, from only errors to everything."""

    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG

    @classmethod
    def from_name(cls, name: str) -> "LogLevel":
        """Find a level by name, ignoring case.

        Raises:
            ValueError: If the name is not a level; the message lists the
                valid names.

        >>> LogLevel.from_name("info")
        <LogLevel.INFO: 20>
        """
        try:
            return cls[name.upper()]
        except KeyError:
            valid = ", ".join(level.name for level in cls)
            message = f"unknown log level {name!r}; use one of: {valid}"
            raise ValueError(message) from None


@dataclass(frozen=True)
class LogSettings:
    """Where to log and how much."""

    level: LogLevel = LogLevel.WARNING
    log_file: Path = Path("arena.log")


def configure_logging(settings: LogSettings) -> None:
    """Send the application's log records at ``settings.level`` to a file.

    Calling it again replaces the previous file handler.

    Args:
        settings: The level and file to use.
    """
    logger = logging.getLogger("arena")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    handler = logging.FileHandler(settings.log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(settings.level.value)
