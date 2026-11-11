"""Tests for running one match at a time for the window."""

import queue
import unittest

from applications import add_broken_bot, make_application, wait_for
from arena.bots.source import BotSource
from arena.gui.match_session import MatchSession, find_saved_match_id
from arena.model.state import ModeKind
from arena.runtime.observers import (
    MatchEvent,
    MatchFailed,
    MatchFinished,
    MatchStarted,
)

MEDIUM = BotSource.builtin("Medium")
EASY = BotSource.builtin("Easy")


class MatchSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.application = make_application(self)
        self.session = MatchSession(self.application)
        self.addCleanup(self.stop_session)
        self.events: list[MatchEvent] = []

    def stop_session(self) -> None:
        self.session.stop()
        wait_for(lambda: not self.session.is_running, 10, self.collect)

    def collect(self) -> None:
        self.events.extend(self.session.poll())

    def ended(self) -> bool:
        return any(
            isinstance(event, MatchFinished | MatchFailed)
            for event in self.events
        )

    def test_session_plays_a_match_and_reports_events(self) -> None:
        self.session.start(ModeKind.DUEL, MEDIUM, EASY, 3)
        self.assertTrue(wait_for(self.ended, 20, self.collect))
        self.assertIsInstance(self.events[0], MatchStarted)
        self.assertIsInstance(self.events[-1], MatchFinished)
        self.assertTrue(
            wait_for(lambda: not self.session.is_running, 5, self.collect)
        )

    def test_second_start_while_running_is_refused(self) -> None:
        self.session.start(ModeKind.DUEL, MEDIUM, EASY, 3)
        with self.assertRaises(RuntimeError):
            self.session.start(ModeKind.DUEL, MEDIUM, EASY, 4)

    def test_stop_ends_the_match(self) -> None:
        self.session.start(ModeKind.DUEL, MEDIUM, EASY, 3)
        self.session.stop()
        self.assertTrue(wait_for(self.ended, 10, self.collect))
        finished = self.events[-1]
        assert isinstance(finished, MatchFinished)
        self.assertTrue(finished.stopped)

    def test_failed_match_reports_error(self) -> None:
        broken = BotSource.from_file(add_broken_bot(self.application))
        self.session.start(ModeKind.DUEL, broken, EASY, 3)
        self.assertTrue(wait_for(self.ended, 10, self.collect))
        failed = self.events[-1]
        assert isinstance(failed, MatchFailed)
        self.assertIn("SyntaxError", failed.message)

    def test_finished_match_can_be_found_in_history(self) -> None:
        self.session.start(ModeKind.DUEL, MEDIUM, EASY, 3)
        self.assertTrue(wait_for(self.ended, 20, self.collect))
        finished = self.events[-1]
        assert isinstance(finished, MatchFinished)
        repository = self.application.repository
        saved = repository.list_matches()[0]
        self.assertEqual(
            find_saved_match_id(repository, finished.match.summary),
            saved.match_id,
        )


class PollTest(unittest.TestCase):
    def test_poll_takes_at_most_fifty_events(self) -> None:
        events: queue.Queue[MatchEvent] = queue.Queue()
        for number in range(120):
            events.put(MatchFailed(str(number)))
        session = MatchSession(make_application(self), events)
        self.assertEqual(
            [len(session.poll()) for _ in range(4)], [50, 50, 20, 0]
        )

    def test_queued_events_keep_the_session_running(self) -> None:
        events: queue.Queue[MatchEvent] = queue.Queue()
        session = MatchSession(make_application(self), events)
        self.assertFalse(session.is_running)
        events.put(MatchFailed("late"))
        self.assertTrue(session.is_running)


if __name__ == "__main__":
    unittest.main()
