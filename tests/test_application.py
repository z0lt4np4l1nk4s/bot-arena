"""Tests for the composition root and the command line."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import main
from arena.application import Application, ApplicationSettings
from arena.bots.source import BotSource
from arena.model.state import ModeKind
from arena.rules import Rules
from arena.storage.repository import InMemoryMatchRepository
from arena.storage.sqlite_repository import SqliteMatchRepository

BOT_FILE = """\
from arena.api import Action, BotState


class ABot:
    name = "A bot"

    def decide(self, state: BotState) -> Action:
        return Action.wait()
"""


class ApplicationTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.user_bots = self.folder / "user_bots"
        self.user_bots.mkdir()
        (self.user_bots / "a_bot.py").write_text(BOT_FILE, encoding="utf-8")
        self.repository = InMemoryMatchRepository()
        settings = ApplicationSettings(
            database=self.folder / "unused.db",
            rules=Rules(
                duel_max_turns=20,
                turn_time_limit_ms=200,
                bot_kill_timeout_ms=600,
            ),
            user_bots_folder=self.user_bots,
        )
        self.application = Application(settings, self.repository)
        self.addCleanup(self.application.close)

    def test_bot_sources_lists_builtins_and_user_files(self) -> None:
        names = [source.name for source in self.application.bot_sources()]
        self.assertEqual(names, ["Easy", "Hard", "Medium", "a_bot"])

    def test_created_match_is_saved_after_running(self) -> None:
        runner = self.application.create_match(
            ModeKind.DUEL,
            BotSource.builtin("Medium"),
            BotSource.builtin("Easy"),
        )
        match = runner.run(5)
        self.assertEqual(len(match.turns), 20)
        self.assertEqual(len(self.repository.list_matches()), 1)

    def test_injected_repository_is_used(self) -> None:
        self.assertIs(self.application.repository, self.repository)


class CommandLineTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.database = self.folder / "history.db"

    def run_main(self, *arguments: str) -> tuple[int, str, str]:
        """Run the command line and capture what it prints."""
        output, errors = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
        ):
            code = main.main(list(arguments))
        return code, output.getvalue(), errors.getvalue()

    def test_main_plays_and_prints_result(self) -> None:
        code, output, _ = self.run_main(
            "play",
            "Medium",
            "Easy",
            "--seed",
            "2",
            "--database",
            str(self.database),
            "--log-file",
            str(self.folder / "arena.log"),
        )
        self.assertEqual(code, 0)
        self.assertIn("Medium", output)
        with SqliteMatchRepository(self.database) as repository:
            self.assertEqual(len(repository.list_matches()), 1)

    def test_main_reports_broken_bot(self) -> None:
        broken = self.folder / "broken.py"
        broken.write_text("def broken(:\n", encoding="utf-8")
        code, _, errors = self.run_main(
            "play",
            str(broken),
            "Easy",
            "--database",
            str(self.database),
            "--log-file",
            str(self.folder / "arena.log"),
        )
        self.assertEqual(code, 2)
        self.assertIn("SyntaxError", errors)


if __name__ == "__main__":
    unittest.main()
