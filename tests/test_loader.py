"""Tests for loading bot classes from user files."""

import tempfile
import textwrap
import unittest
from pathlib import Path

from arena.bots.loader import load_bot_class
from arena.bots.protocol import Bot
from arena.errors import BotLoadError

GOOD_BOT = """\
from arena.api import Action, BotState


class MyBot:
    name = "My bot"

    def decide(self, state: BotState) -> Action:
        return Action.wait("thinking")
"""


class LoadBotClassTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)

    def write(self, source: str, name: str = "bot.py") -> Path:
        """Write a bot file into the temporary folder."""
        path = self.folder / name
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return path

    def load_error(self, source: str) -> BotLoadError:
        """Load ``source`` and return the error it must raise."""
        with self.assertRaises(BotLoadError) as context:
            load_bot_class(self.write(source))
        return context.exception

    def test_loads_single_bot_class(self) -> None:
        bot_class = load_bot_class(self.write(GOOD_BOT))
        self.assertEqual(bot_class.__name__, "MyBot")

    def test_loaded_class_satisfies_protocol(self) -> None:
        bot_class = load_bot_class(self.write(GOOD_BOT))
        self.assertIsInstance(bot_class(), Bot)

    def test_syntax_error_reports_line(self) -> None:
        error = self.load_error("x = 1\ny = 2\ndef broken(:\n")
        self.assertEqual(error.line, 3)
        self.assertIn("SyntaxError", str(error))
        self.assertIn("(line 3)", str(error))

    def test_import_time_exception_reports_line(self) -> None:
        error = self.load_error("x = 1\n\nvalue = 1 / 0\n")
        self.assertEqual(error.line, 3)
        self.assertIn("ZeroDivisionError", str(error))

    def test_no_bot_class(self) -> None:
        error = self.load_error("class Helper:\n    pass\n")
        self.assertIn("no bot class found", str(error))

    def test_two_bot_classes(self) -> None:
        error = self.load_error(
            GOOD_BOT
            + "\n\nclass Other:\n    name = 'Other'\n\n"
            + "    def decide(self, state):\n        return None\n"
        )
        self.assertIn("several bot classes found: MyBot, Other", str(error))

    def test_imported_class_is_not_counted(self) -> None:
        source = "from collections import OrderedDict\n\n" + GOOD_BOT
        self.assertEqual(load_bot_class(self.write(source)).__name__, "MyBot")

    def test_class_without_decide_is_ignored(self) -> None:
        source = GOOD_BOT + "\n\nclass Helper:\n    name = 'helper'\n"
        self.assertEqual(load_bot_class(self.write(source)).__name__, "MyBot")

    def test_constructor_with_arguments_is_rejected(self) -> None:
        source = GOOD_BOT.replace(
            '    name = "My bot"\n',
            '    name = "My bot"\n\n'
            "    def __init__(self, speed: int) -> None:\n"
            "        self.speed = speed\n",
        )
        error = self.load_error(source)
        self.assertIn("constructible without arguments", str(error))

    def test_two_files_with_same_class_name_do_not_clash(self) -> None:
        first = load_bot_class(self.write(GOOD_BOT, "first.py"))
        second_source = GOOD_BOT.replace('"thinking"', '"other"')
        second = load_bot_class(self.write(second_source, "second.py"))
        self.assertIsNot(first, second)

    def test_dataclass_with_future_annotations_loads(self) -> None:
        source = (
            "from __future__ import annotations\n\n"
            "from dataclasses import dataclass\n\n"
            "@dataclass\nclass Memory:\n    seen: int = 0\n\n" + GOOD_BOT
        )
        self.assertEqual(load_bot_class(self.write(source)).__name__, "MyBot")

    def test_exit_at_import_is_a_load_error(self) -> None:
        error = self.load_error("import sys\nsys.exit(3)\n")
        self.assertIn("SystemExit", str(error))

    def test_missing_file_is_a_load_error(self) -> None:
        with self.assertRaises(BotLoadError):
            load_bot_class(self.folder / "missing.py")


if __name__ == "__main__":
    unittest.main()
