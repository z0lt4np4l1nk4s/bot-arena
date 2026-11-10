"""Tests for running a bot in its own process with a time limit.

These tests start real processes, so each takes a moment.
"""

import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from arena.bots.source import BotSource
from arena.engine.modes import Duel
from arena.errors import BotLoadError
from arena.model.actions import Action, ActionKind
from arena.model.geometry import Direction
from arena.model.side import Side
from arena.model.state import BotState
from arena.rules import Rules
from arena.runtime.bot_process import BotProcess, BotReply

RULES = Rules(turn_time_limit_ms=200, bot_kill_timeout_ms=600)
BOT_FILES = Path(__file__).parent / "bot_files"


def state_at(turn: int) -> BotState:
    """A real bot view from a duel, with the given turn number."""
    duel = Duel(RULES)
    view = duel.state_for_bot(duel.setup_map(1), Side.BLUE)
    return replace(view, turn=turn)


class BotProcessTest(unittest.TestCase):
    def start(self, source: BotSource) -> BotProcess:
        """Start a bot process that is stopped after the test."""
        process = BotProcess(source, RULES)
        self.addCleanup(process.stop)
        process.start()
        return process

    def file_bot(self, name: str) -> BotProcess:
        """Start one of the bots in ``tests/bot_files``."""
        return self.start(BotSource.from_file(BOT_FILES / f"{name}.py"))

    def test_good_bot_answers_with_its_action(self) -> None:
        reply = self.file_bot("good").ask(1, state_at(1))
        self.assertEqual(
            reply.action, Action.move(Direction.RIGHT, "going right")
        )
        self.assertIsNone(reply.error)
        self.assertFalse(reply.timed_out)
        self.assertGreaterEqual(reply.elapsed_ms, 0)
        self.assertEqual(reply.turn, 1)

    def test_builtin_bot_runs_in_process(self) -> None:
        reply = self.start(BotSource.builtin("Medium")).ask(1, state_at(1))
        self.assertIs(reply.action.kind, ActionKind.MOVE)

    def test_broken_file_fails_at_start_with_line(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "broken.py"
            path.write_text("x = 1\ndef broken(:\n", encoding="utf-8")
            process = BotProcess(BotSource.from_file(path), RULES)
            self.addCleanup(process.stop)
            with self.assertRaises(BotLoadError) as context:
                process.start()
        self.assertEqual(context.exception.line, 2)

    def test_exception_reports_line_in_bot_file(self) -> None:
        reply = self.file_bot("crashing").ask(1, state_at(1))
        self.assertEqual(reply.action, Action.wait())
        assert reply.error is not None
        self.assertIn("ZeroDivisionError", reply.error)
        self.assertIn("(line 10)", reply.error)

    def test_wrong_return_type_is_an_error(self) -> None:
        reply = self.file_bot("wrong_type").ask(1, state_at(1))
        self.assertEqual(reply.action, Action.wait())
        self.assertEqual(
            reply.error, "decide() must return an Action, got str"
        )

    def test_slow_bot_times_out(self) -> None:
        reply = self.file_bot("slow").ask(1, state_at(1))
        self.assertTrue(reply.timed_out)
        self.assertEqual(reply.action, Action.wait())

    def test_late_reply_is_discarded(self) -> None:
        process = self.file_bot("slow")
        process.ask(1, state_at(1))
        time.sleep(0.5)
        reply = process.ask(2, state_at(2))
        self.assertEqual(reply.turn, 2)
        self.assertNotEqual(reply.action.message, "answer for turn 1")

    def test_hanging_bot_is_restarted(self) -> None:
        process = self.file_bot("hanging")
        process.ask(1, state_at(1))
        turn = 2
        started = time.monotonic()
        reply: BotReply | None = None
        while time.monotonic() - started < 5:
            reply = process.ask(turn, state_at(turn))
            if not reply.timed_out:
                break
            turn += 1
        self.assertEqual(process.restarts, 1)
        assert reply is not None
        self.assertEqual(reply.action.message, f"awake in turn {turn}")

    def test_stop_is_idempotent_and_kills_child(self) -> None:
        process = self.file_bot("good")
        process.stop()
        process.stop()
        self.assertFalse(process.is_alive)


if __name__ == "__main__":
    unittest.main()
