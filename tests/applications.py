"""An application for tests: in-memory history, short and fast rules."""

import tempfile
import time
import unittest
from collections.abc import Callable
from pathlib import Path

from arena.application import Application, ApplicationSettings
from arena.rules import Rules
from arena.storage.repository import InMemoryMatchRepository

SHORT_RULES = Rules(
    turn_time_limit_ms=200,
    bot_kill_timeout_ms=600,
    duel_max_turns=20,
    solo_max_turns=20,
)
BROKEN_BOT = "def broken(:\n"


def make_application(
    test_case: unittest.TestCase, rules: Rules = SHORT_RULES
) -> Application:
    """An application whose user bots live in a temporary folder."""
    folder = tempfile.TemporaryDirectory()
    test_case.addCleanup(folder.cleanup)
    user_bots = Path(folder.name) / "user_bots"
    user_bots.mkdir()
    settings = ApplicationSettings(
        database=Path(folder.name) / "unused.db",
        rules=rules,
        user_bots_folder=user_bots,
    )
    application = Application(settings, InMemoryMatchRepository())
    test_case.addCleanup(application.close)
    return application


def add_broken_bot(application: Application) -> Path:
    """Write a user bot with a syntax error and return its path."""
    path = application.settings.user_bots_folder / "broken.py"
    path.write_text(BROKEN_BOT, encoding="utf-8")
    return path


def wait_for(
    condition: Callable[[], bool],
    seconds: float,
    step: Callable[[], object] = lambda: None,
) -> bool:
    """Call ``step`` until ``condition`` holds or ``seconds`` pass.

    Returns:
        Whether the condition became true in time.
    """
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        step()
        if condition():
            return True
        time.sleep(0.01)
    return condition()
