"""Tests for playing whole matches with the match runner."""

import tempfile
import threading
import time
import unittest
from pathlib import Path

from arena.bots.builtin.hard import HardBot
from arena.bots.builtin.medium import MediumBot
from arena.bots.source import BotSource
from arena.engine.modes import Duel, Solo
from arena.errors import BotLoadError
from arena.model.actions import Action
from arena.model.side import Side
from arena.model.state import BotState, GameState
from arena.rules import Rules
from arena.runtime.bot_process import BotProcess, BotReply
from arena.runtime.clients import BotClient, InProcessBotClient
from arena.runtime.match_runner import MatchRunner
from arena.storage.records import MatchSummary, RecordedMatch, TurnRecord

PROCESS_RULES = Rules(
    turn_time_limit_ms=200, bot_kill_timeout_ms=600, duel_max_turns=30
)


class FakeClient:
    """A bot client that waits, then answers ``wait`` (or an error)."""

    def __init__(
        self, name: str, delay: float = 0.0, error: str | None = None
    ) -> None:
        self.name = name
        self.delay = delay
        self.error = error
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def ask(self, turn: int, state: BotState) -> BotReply:
        time.sleep(self.delay)
        return BotReply(turn, Action.wait(), self.delay * 1000, self.error)

    def stop(self) -> None:
        self.stopped = True


class RecordingObserver:
    """Remembers everything the runner reports."""

    def __init__(self) -> None:
        self.started: list[MatchSummary] = []
        self.turns: list[int] = []
        self.finished: list[bool] = []

    def on_match_started(
        self, summary: MatchSummary, initial_state: GameState
    ) -> None:
        self.started.append(summary)

    def on_turn(self, record: TurnRecord) -> None:
        self.turns.append(record.turn)

    def on_match_finished(self, match: RecordedMatch, stopped: bool) -> None:
        self.finished.append(stopped)


class FailingObserver(RecordingObserver):
    """An observer that breaks on every turn."""

    def on_turn(self, record: TurnRecord) -> None:
        message = "observer broke"
        raise RuntimeError(message)


class StoppingObserver(RecordingObserver):
    """Sets the stop event after turn 3."""

    def __init__(self, stop_event: threading.Event) -> None:
        super().__init__()
        self.stop_event = stop_event

    def on_turn(self, record: TurnRecord) -> None:
        super().on_turn(record)
        if record.turn == 3:
            self.stop_event.set()


def in_process(blue: BotClient, red: BotClient) -> dict[Side, BotClient]:
    """Clients for both sides."""
    return {Side.BLUE: blue, Side.RED: red}


class MatchRunnerTest(unittest.TestCase):
    def test_runs_a_full_duel(self) -> None:
        duel = Duel()
        clients = in_process(
            InProcessBotClient(HardBot()), InProcessBotClient(MediumBot())
        )
        match = MatchRunner(duel, clients).run(4)
        final = match.turns[-1].state
        self.assertEqual(match.summary.turns, final.turn)
        self.assertEqual(match.summary.winner, duel.winner(final))
        self.assertEqual(
            match.summary.bots, {Side.BLUE: "Hard", Side.RED: "Medium"}
        )
        self.assertTrue(final.is_finished)

    def test_runs_a_full_solo(self) -> None:
        clients: dict[Side, BotClient] = {
            Side.BLUE: InProcessBotClient(MediumBot())
        }
        match = MatchRunner(Solo(), clients).run(2)
        self.assertEqual(match.summary.bots, {Side.BLUE: "Medium"})
        self.assertIsNotNone(match.summary.solo_turns_used)

    def test_observers_see_every_turn_in_order(self) -> None:
        observer = RecordingObserver()
        clients = in_process(FakeClient("A"), FakeClient("B"))
        match = MatchRunner(
            Duel(Rules(duel_max_turns=12)), clients, [observer]
        ).run(1)
        self.assertEqual(len(observer.started), 1)
        self.assertEqual(observer.turns, list(range(1, 13)))
        self.assertEqual(observer.finished, [False])
        self.assertEqual(len(match.turns), 12)

    def test_failing_observer_does_not_stop_the_match(self) -> None:
        second = RecordingObserver()
        clients = in_process(FakeClient("A"), FakeClient("B"))
        runner = MatchRunner(
            Duel(Rules(duel_max_turns=5)), clients, [FailingObserver(), second]
        )
        with self.assertLogs("arena.runtime", "ERROR"):
            runner.run(1)
        self.assertEqual(second.turns, [1, 2, 3, 4, 5])

    def test_bot_error_is_recorded_in_the_turn(self) -> None:
        clients = in_process(
            FakeClient("A", error="boom (line 3)"), FakeClient("B")
        )
        match = MatchRunner(Duel(Rules(duel_max_turns=2)), clients).run(1)
        self.assertEqual(
            match.turns[0].replies[Side.BLUE].error, "boom (line 3)"
        )

    def test_clients_are_started_and_stopped(self) -> None:
        blue, red = FakeClient("A"), FakeClient("B")
        MatchRunner(Duel(Rules(duel_max_turns=2)), in_process(blue, red)).run(
            1
        )
        self.assertTrue(blue.started and red.started)
        self.assertTrue(blue.stopped and red.stopped)

    def test_stop_event_ends_the_match_early(self) -> None:
        stop_event = threading.Event()
        observer = StoppingObserver(stop_event)
        clients = in_process(FakeClient("A"), FakeClient("B"))
        match = MatchRunner(Duel(), clients, [observer]).run(1, stop_event)
        self.assertEqual(len(match.turns), 3)
        self.assertEqual(observer.finished, [True])

    def test_bots_are_asked_in_parallel(self) -> None:
        clients = in_process(FakeClient("A", 0.15), FakeClient("B", 0.15))
        started = time.monotonic()
        MatchRunner(Duel(Rules(duel_max_turns=5)), clients).run(1)
        self.assertLess(time.monotonic() - started, 1.25)


class RealProcessesTest(unittest.TestCase):
    def test_real_processes_play_a_match(self) -> None:
        clients = in_process(
            BotProcess(BotSource.builtin("Medium"), PROCESS_RULES),
            BotProcess(BotSource.builtin("Easy"), PROCESS_RULES),
        )
        match = MatchRunner(Duel(PROCESS_RULES), clients).run(3)
        self.assertEqual(len(match.turns), 30)

    def test_processes_are_stopped_even_if_a_bot_fails_to_start(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            broken = Path(folder) / "broken.py"
            broken.write_text("def broken(:\n", encoding="utf-8")
            blue = BotProcess(BotSource.builtin("Medium"), PROCESS_RULES)
            red = BotProcess(BotSource.from_file(broken), PROCESS_RULES)
            runner = MatchRunner(Duel(PROCESS_RULES), in_process(blue, red))
            with self.assertRaises(BotLoadError):
                runner.run(1)
        self.assertFalse(blue.is_alive)
        self.assertFalse(red.is_alive)


if __name__ == "__main__":
    unittest.main()
