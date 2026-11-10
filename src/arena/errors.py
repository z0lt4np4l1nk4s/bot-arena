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
