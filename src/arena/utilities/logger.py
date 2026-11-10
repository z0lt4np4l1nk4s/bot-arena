"""The application's logger: one place for log levels, format and file.

Every module gets its logger with :func:`get_logger` instead of using the
``logging`` module directly, and :func:`configure_logging` is called once
at start-up. Only the ``arena`` logger tree is configured, so other
libraries' logging is left alone.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

ROOT_LOGGER_NAME: Final = "arena"
DEFAULT_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


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
    """How much to log, where, and in which format."""

    level: LogLevel = LogLevel.WARNING
    log_file: Path = Path("arena.log")
    message_format: str = DEFAULT_FORMAT


def configure_logging(settings: LogSettings) -> None:
    """Send the application's log records at ``settings.level`` to a file.

    Calling it again replaces the previous file handler.

    Args:
        settings: The level, file and format to use.
    """
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    handler = logging.FileHandler(settings.log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter(settings.message_format))
    logger.addHandler(handler)
    logger.setLevel(settings.level.value)


def get_logger(component: str) -> logging.Logger:
    """Return the logger of one part of the application.

    Args:
        component: A short name such as ``"runtime"`` or ``"engine"``.

    Returns:
        The logger ``arena.<component>``, configured by
        :func:`configure_logging`.

    >>> get_logger("runtime").name
    'arena.runtime'
    """
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{component}")
