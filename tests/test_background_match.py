"""Tests for running a match in a background thread."""

import queue
import time
import unittest

from arena.engine.modes import Duel
from arena.model.side import Side
from arena.rules import Rules
from arena.runtime.match_runner import MatchRunner
from arena.runtime.observers import (
    MatchEvent,
    MatchFailed,
    MatchFinished,
    MatchStarted,
    QueueObserver,
    TurnPlayed,
)
from test_match_runner import FakeClient, RecordingObserver


class BrokenStartClient(FakeClient):
    """A client that cannot start."""

    def start(self) -> None:
        message = "cannot start"
        raise RuntimeError(message)


def drain(events: "queue.Queue[MatchEvent]") -> list[MatchEvent]:
    """Take every event currently in the queue."""
    items: list[MatchEvent] = []
    while not events.empty():
        items.append(events.get_nowait())
    return items


class BackgroundMatchTest(unittest.TestCase):
    def test_background_match_finishes_and_returns_result(self) -> None:
        runner = MatchRunner(
            Duel(Rules(duel_max_turns=10)),
            {Side.BLUE: FakeClient("A"), Side.RED: FakeClient("B")},
        )
        handle = runner.run_in_background(1)
        match = handle.join(5)
        assert match is not None
        self.assertEqual(len(match.turns), 10)
        self.assertFalse(handle.is_running)
        self.assertIsNone(handle.error)

    def test_queue_receives_events_in_order(self) -> None:
        events: queue.Queue[MatchEvent] = queue.Queue()
        runner = MatchRunner(
            Duel(Rules(duel_max_turns=4)),
            {Side.BLUE: FakeClient("A"), Side.RED: FakeClient("B")},
            [QueueObserver(events)],
        )
        runner.run_in_background(1).join(5)
        items = drain(events)
        self.assertIsInstance(items[0], MatchStarted)
        turns = [
            item.record.turn for item in items if isinstance(item, TurnPlayed)
        ]
        self.assertEqual(turns, [1, 2, 3, 4])
        last = items[-1]
        assert isinstance(last, MatchFinished)
        self.assertFalse(last.stopped)

    def test_stop_ends_the_match_quickly(self) -> None:
        observer = RecordingObserver()
        runner = MatchRunner(
            Duel(),
            {
                Side.BLUE: FakeClient("A", 0.05),
                Side.RED: FakeClient("B", 0.05),
            },
            [observer],
        )
        handle = runner.run_in_background(1)
        time.sleep(0.3)
        stopped_at = time.monotonic()
        handle.stop()
        match = handle.join(2)
        self.assertLess(time.monotonic() - stopped_at, 0.5)
        assert match is not None
        self.assertLess(len(match.turns), 200)
        self.assertEqual(observer.finished, [True])

    def test_thread_error_is_reported(self) -> None:
        events: queue.Queue[MatchEvent] = queue.Queue()
        runner = MatchRunner(
            Duel(Rules(duel_max_turns=4)),
            {Side.BLUE: BrokenStartClient("A"), Side.RED: FakeClient("B")},
            [QueueObserver(events)],
        )
        with self.assertLogs("arena.runtime", "ERROR"):
            handle = runner.run_in_background(1)
            result = handle.join(5)
        self.assertIsNone(result)
        self.assertIsInstance(handle.error, RuntimeError)
        failures = [
            item for item in drain(events) if isinstance(item, MatchFailed)
        ]
        self.assertEqual(len(failures), 1)
        self.assertIn("cannot start", failures[0].message)


if __name__ == "__main__":
    unittest.main()
