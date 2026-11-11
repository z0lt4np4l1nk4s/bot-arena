"""Exceptions raised by the application.

Every project error derives from :class:`ArenaError`, so callers can catch
all of them with a single ``except`` clause.
"""


class ArenaError(Exception):
    """Base class for all errors raised by Bot Arena."""


class RulesError(ArenaError):
    """Raised when game rules are given an invalid value."""


class InvalidActionError(ArenaError):
    """Raised when an action is built with inconsistent fields."""


class MapGenerationError(ArenaError):
    """Raised when no valid map can be generated for the given rules."""


class SchemaVersionError(ArenaError):
    """Raised when a database was written by a newer version."""


class BotLoadError(ArenaError):
    """Raised when a bot cannot be loaded; ``line`` is in the bot's file."""

    def __init__(self, message: str, line: int | None = None) -> None:
        """Create the error.

        Args:
            message: What went wrong.
            line: The line in the bot's file, if known.
        """
        suffix = f" (line {line})" if line is not None else ""
        super().__init__(f"{message}{suffix}")
        self.reason = message
        self.line = line
