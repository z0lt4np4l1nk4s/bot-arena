"""Tests for the texts and lines the match viewer shows."""

import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from arena.bots.source import BotSource
from arena.gui.formatting import (
    LogRow,
    bot_label,
    describe_action,
    log_rows,
    player_status,
    result_text,
    score_text,
    shot_lines,
)
from arena.model.actions import Action
from arena.model.geometry import Direction, Position
from arena.model.replies import BotReply
from arena.model.side import Side
from arena.model.state import Event, EventKind, ModeKind
from arena.rules import Rules
from arena.storage.records import MatchSummary, TurnRecord
from builders import make_state, with_player

RULES = Rules(grid_size=10)
EMPTY = "." * 10
DUEL = make_state(
    [".B..R.....", *[EMPTY] * 9], rules=RULES
)  # Blue at (1, 0), Red at (4, 0)


def summary(**changes: object) -> MatchSummary:
    """A finished duel summary with some fields changed."""
    base = MatchSummary(
        match_id=1,
        played_at=datetime(2026, 11, 11, 14, 5),
        mode=ModeKind.DUEL,
        seed=3,
        bots={Side.BLUE: "Hard", Side.RED: "Medium"},
        winner=Side.BLUE,
        delivered={Side.BLUE: 9, Side.RED: 7},
        turns=170,
        solo_turns_used=None,
    )
    # Field names and values vary per test, so they cannot be typed here.
    return replace(base, **changes)  # type: ignore[arg-type]


class DescribeActionTest(unittest.TestCase):
    def test_every_kind_of_action(self) -> None:
        cases = [
            (Action.move(Direction.RIGHT), "move right"),
            (Action.shoot(Direction.UP), "shoot up"),
            (Action.trap(Position(4, 5)), "trap at (4, 5)"),
            (Action.wait(), "wait"),
        ]
        for action, text in cases:
            with self.subTest(text=text):
                self.assertEqual(describe_action(action), text)


class LogRowsTest(unittest.TestCase):
    def test_one_row_per_side_blue_first(self) -> None:
        record = TurnRecord(
            5,
            DUEL,
            {
                Side.RED: BotReply(5, Action.wait(), 3.0),
                Side.BLUE: BotReply(
                    5, Action.move(Direction.LEFT, "home"), 12.345
                ),
            },
        )
        self.assertEqual(
            log_rows(record),
            [
                LogRow(5, Side.BLUE, "move left", "home", "12.3", ""),
                LogRow(5, Side.RED, "wait", "", "3.0", ""),
            ],
        )

    def test_log_rows_show_timeout_and_error(self) -> None:
        record = TurnRecord(
            2,
            DUEL,
            {
                Side.BLUE: BotReply(2, Action.wait(), 100.0, timed_out=True),
                Side.RED: BotReply(2, Action.wait(), 0.0, error="boom"),
            },
        )
        problems = [row.problem for row in log_rows(record)]
        self.assertEqual(problems, ["timed out", "boom"])


class PlayerStatusTest(unittest.TestCase):
    def test_ready_bot(self) -> None:
        state = with_player(DUEL, Side.BLUE, carrying=2)
        self.assertEqual(
            player_status(state.player(Side.BLUE), RULES),
            "carrying 2/3 · shot ready · traps 3",
        )

    def test_cooling_down_and_disabled(self) -> None:
        state = with_player(
            DUEL,
            Side.RED,
            shoot_cooldown=4,
            stunned_turns=2,
            trapped_turns=3,
            free_traps=1,
        )
        self.assertEqual(
            player_status(state.player(Side.RED), RULES),
            "carrying 0/3 · shot in 4 · traps 1 · stunned 2 · trapped 3",
        )


class ScoreTextTest(unittest.TestCase):
    def test_duel_score(self) -> None:
        state = with_player(DUEL, Side.BLUE, delivered=3)
        state = with_player(state, Side.RED, delivered=2)
        self.assertEqual(score_text(state), "Blue 3 : 2 Red")

    def test_solo_score_counts_all_crystals(self) -> None:
        solo = make_state(["B.2.......", *[EMPTY] * 9], rules=RULES)
        solo = with_player(solo, Side.BLUE, delivered=3, carrying=1)
        # 3 delivered + 1 carried + 2 on the ground.
        self.assertEqual(score_text(solo), "Delivered 3 of 6")


class BotLabelTest(unittest.TestCase):
    def test_builtin_and_user_bots(self) -> None:
        self.assertEqual(
            bot_label(BotSource.builtin("Hard")), "Hard (built-in)"
        )
        self.assertEqual(
            bot_label(BotSource.from_file(Path("user_bots/my_bot.py"))),
            "my_bot",
        )


class ResultTextTest(unittest.TestCase):
    def test_duel_results(self) -> None:
        cases = [
            (summary(), "Blue wins 9:7"),
            (
                summary(
                    winner=Side.RED, delivered={Side.BLUE: 2, Side.RED: 5}
                ),
                "Red wins 2:5",
            ),
            (
                summary(winner=None, delivered={Side.BLUE: 8, Side.RED: 8}),
                "Draw 8:8",
            ),
        ]
        for value, text in cases:
            with self.subTest(text=text):
                self.assertEqual(result_text(value), text)

    def test_solo_results(self) -> None:
        finished = summary(
            mode=ModeKind.SOLO,
            bots={Side.BLUE: "Medium"},
            winner=None,
            delivered={Side.BLUE: 8},
            solo_turns_used=104,
        )
        unfinished = replace(
            finished, delivered={Side.BLUE: 5}, solo_turns_used=None
        )
        self.assertEqual(result_text(finished), "Finished in 104 turns")
        self.assertEqual(result_text(unfinished), "Not finished (5 delivered)")


class ShotLinesTest(unittest.TestCase):
    def test_shot_lines_from_shooter_to_end(self) -> None:
        shot = Event(EventKind.SHOT, Side.BLUE, Position(4, 0))
        state = replace(DUEL, events=(shot,))
        self.assertEqual(
            shot_lines(state),
            [(Side.BLUE, [Position(2, 0), Position(3, 0), Position(4, 0)])],
        )

    def test_shot_into_adjacent_wall_has_no_line(self) -> None:
        shot = Event(EventKind.SHOT, Side.RED, Position(4, 0))
        state = replace(DUEL, events=(shot,))
        self.assertEqual(shot_lines(state), [(Side.RED, [])])

    def test_turn_without_shots(self) -> None:
        self.assertEqual(shot_lines(DUEL), [])


if __name__ == "__main__":
    unittest.main()
