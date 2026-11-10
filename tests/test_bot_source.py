"""Tests for creating bots from their source (built-in or file)."""

import pickle
import tempfile
import unittest
from pathlib import Path

from arena.bots.source import BotSource
from arena.errors import BotLoadError

BOT_FILE = """\
from arena.api import Action, BotState


class MyBot:
    name = "My bot"

    def decide(self, state: BotState) -> Action:
        return Action.wait()
"""


class BotSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "clever_bot.py"
        self.path.write_text(BOT_FILE, encoding="utf-8")

    def test_builtin_source_creates_bot(self) -> None:
        self.assertEqual(BotSource.builtin("Medium").create().name, "Medium")

    def test_file_source_creates_bot(self) -> None:
        self.assertEqual(
            BotSource.from_file(self.path).create().name, "My bot"
        )

    def test_file_source_name_is_file_stem(self) -> None:
        self.assertEqual(BotSource.from_file(self.path).name, "clever_bot")

    def test_unknown_builtin_raises(self) -> None:
        with self.assertRaises(BotLoadError):
            BotSource.builtin("Genius").create()

    def test_sources_are_picklable(self) -> None:
        for source in [
            BotSource.builtin("Hard"),
            BotSource.from_file(self.path),
        ]:
            with self.subTest(source=source.name):
                self.assertEqual(pickle.loads(pickle.dumps(source)), source)


if __name__ == "__main__":
    unittest.main()
