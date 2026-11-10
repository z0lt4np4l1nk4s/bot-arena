"""The registry of built-in bots, filled by a class decorator."""

import importlib
from typing import TypeVar

from arena.bots.protocol import Bot

B = TypeVar("B", bound=Bot)

_registry: dict[str, type[Bot]] = {}


def register_builtin(bot_class: type[B]) -> type[B]:
    """Add a built-in bot class to the registry under its ``name``.

    Args:
        bot_class: A class that satisfies the :class:`Bot` protocol.

    Returns:
        The same class, so this can be used as a decorator.

    Raises:
        TypeError: If the class is not a bot or its name is taken.
    """
    name = getattr(bot_class, "name", None)
    if not isinstance(name, str) or not callable(
        getattr(bot_class, "decide", None)
    ):
        message = f"{bot_class.__name__} does not satisfy the Bot protocol"
        raise TypeError(message)
    if name in _registry:
        message = f"a built-in bot named {name!r} is already registered"
        raise TypeError(message)
    _registry[name] = bot_class
    return bot_class


def builtin_bots() -> dict[str, type[Bot]]:
    """Return every built-in bot class by name.

    >>> sorted(builtin_bots())
    ['Easy', 'Hard', 'Medium']
    """
    # Importing the package runs the decorators that fill the registry.
    importlib.import_module("arena.bots.builtin")
    return dict(_registry)
