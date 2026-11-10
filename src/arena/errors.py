"""Exceptions raised by the application.

Every project error derives from :class:`ArenaError`, so callers can catch
all of them with a single ``except`` clause.
"""


class ArenaError(Exception):
    """Base class for all errors raised by Bot Arena."""


class RulesError(ArenaError):
    """Raised when game rules are given an invalid value."""
