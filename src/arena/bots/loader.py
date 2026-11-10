"""Load a bot class from a user's ``.py`` file.

The file is imported as a fresh module, and the one class defined in it
that looks like a bot is returned. Every problem becomes a
:class:`BotLoadError` that points at the line in the user's file.
"""

import importlib.util
import inspect
import itertools
import sys
import traceback
from pathlib import Path
from types import ModuleType
from typing import Final, TypeGuard

from arena.bots.protocol import Bot
from arena.errors import BotLoadError

_module_numbers: Final = itertools.count()


def load_bot_class(path: Path) -> type[Bot]:
    """Import ``path`` and return the bot class defined in it.

    Args:
        path: The bot's ``.py`` file.

    Returns:
        The only class defined in the file that has a ``name`` string and
        a ``decide`` method.

    Raises:
        BotLoadError: If the file cannot be read or run, or it does not
            define exactly one usable bot class.
    """
    module = _import_file(path)
    candidates = [
        member
        for _, member in inspect.getmembers(module, inspect.isclass)
        if member.__module__ == module.__name__ and _looks_like_bot(member)
    ]
    if not candidates:
        message = "no bot class found (a class with 'name' and 'decide')"
        raise BotLoadError(message)
    if len(candidates) > 1:
        names = ", ".join(sorted(member.__name__ for member in candidates))
        message = f"several bot classes found: {names}"
        raise BotLoadError(message)
    bot_class = candidates[0]
    _check_constructible(bot_class)
    return bot_class


def error_line_in_file(error: BaseException, path: Path) -> int | None:
    """Return the line of ``path`` closest to where ``error`` happened.

    Args:
        error: An exception, usually raised by user code.
        path: The user's file.

    Returns:
        The line number in that file, or ``None`` if the error did not
        pass through it.
    """
    if isinstance(error, SyntaxError) and error.lineno is not None:
        return error.lineno
    target = path.resolve()
    lines = [
        frame.lineno
        for frame in traceback.extract_tb(error.__traceback__)
        if Path(frame.filename).resolve() == target
    ]
    return lines[-1] if lines else None


def describe_error(error: BaseException) -> str:
    """Return ``"Type: text"`` for an error, even if its text fails.

    User code may raise exceptions whose ``__str__`` itself raises.

    >>> describe_error(ValueError("bad value"))
    'ValueError: bad value'
    """
    if isinstance(error, SyntaxError) and error.msg:
        text = error.msg
    else:
        try:
            text = str(error)
        except Exception:
            text = "<error text could not be shown>"
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


def _import_file(path: Path) -> ModuleType:
    """Run the file as a new module with a unique name."""
    module_name = f"arena_user_bot_{next(_module_numbers)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        message = f"cannot load {path.name}"
        raise BotLoadError(message)
    module = importlib.util.module_from_spec(spec)
    # Registered while it runs, as a normal import would be; features
    # such as dataclasses look the module up by name.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except FileNotFoundError as error:
        sys.modules.pop(module_name, None)
        message = f"file not found: {path.name}"
        raise BotLoadError(message) from error
    # User code may raise anything, including SystemExit from sys.exit().
    except (Exception, SystemExit) as error:
        sys.modules.pop(module_name, None)
        line = error_line_in_file(error, path)
        raise BotLoadError(describe_error(error), line) from error
    return module


def _looks_like_bot(member: type) -> TypeGuard[type[Bot]]:
    """Whether a class has a string ``name`` and a callable ``decide``."""
    name = getattr(member, "name", None)
    return isinstance(name, str) and callable(getattr(member, "decide", None))


def _check_constructible(bot_class: type[Bot]) -> None:
    """Make sure the class can be created without arguments."""
    try:
        inspect.signature(bot_class).bind()
    except (TypeError, ValueError) as error:
        message = "bot class must be constructible without arguments"
        raise BotLoadError(message) from error
