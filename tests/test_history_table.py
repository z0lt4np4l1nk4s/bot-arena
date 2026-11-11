"""Tests for the rows, sorting and filters of the history table."""

import unittest
from dataclasses import replace
from datetime import datetime

from arena.gui.history_table import (
    bot_names,
    filter_summaries,
    history_row,
    solo_record_row,
    sort_summaries,
)
from arena.model.side import Side
from arena.model.state import ModeKind
from arena.storage.records import MatchSummary, SoloRecord

DUEL = MatchSummary(
    match_id=1,
    played_at=datetime(2026, 11, 11, 14, 5, 30),
    mode=ModeKind.DUEL,
    seed=9,
    bots={Side.BLUE: "Hard", Side.RED: "Medium"},
    winner=Side.BLUE,
    delivered={Side.BLUE: 9, Side.RED: 7},
    turns=170,
    solo_turns_used=None,
)
SOLO = MatchSummary(
    match_id=2,
    played_at=datetime(2026, 11, 10, 9, 0),
    mode=ModeKind.SOLO,
    seed=10,
    bots={Side.BLUE: "my_bot"},
    winner=None,
    delivered={Side.BLUE: 8},
    turns=104,
    solo_turns_used=104,
)
LATER = replace(
    DUEL,
    match_id=3,
    played_at=datetime(2026, 12, 1, 8, 0),
    seed=100,
    bots={Side.BLUE: "Easy", Side.RED: "my_bot"},
    turns=200,
)
ALL = [DUEL, SOLO, LATER]


def ids(summaries: list[MatchSummary]) -> list[int | None]:
    return [summary.match_id for summary in summaries]


class HistoryRowTest(unittest.TestCase):
    def test_row_for_duel_and_solo(self) -> None:
        self.assertEqual(
            history_row(DUEL),
            (
                "2026-11-11 14:05",
                "Duel",
                "Hard",
                "Medium",
                "9",
                "Blue wins 9:7",
                "170",
            ),
        )
        self.assertEqual(
            history_row(SOLO),
            (
                "2026-11-10 09:00",
                "Solo",
                "my_bot",
                "-",
                "10",
                "Finished in 104 turns",
                "104",
            ),
        )

    def test_solo_record_row(self) -> None:
        record = SoloRecord(5, 61, "Hard", datetime(2026, 11, 11, 7, 30))
        self.assertEqual(
            solo_record_row(record), ("5", "61", "Hard", "2026-11-11 07:30")
        )


class SortTest(unittest.TestCase):
    def test_sort_by_seed_is_numeric(self) -> None:
        self.assertEqual(ids(sort_summaries(ALL, "seed", False)), [1, 2, 3])

    def test_sort_by_turns_is_numeric(self) -> None:
        self.assertEqual(ids(sort_summaries(ALL, "turns", False)), [2, 1, 3])

    def test_sort_by_date_is_chronological(self) -> None:
        self.assertEqual(ids(sort_summaries(ALL, "date", False)), [2, 1, 3])

    def test_sort_by_text_column(self) -> None:
        self.assertEqual(ids(sort_summaries(ALL, "blue", False)), [3, 1, 2])

    def test_descending_reverses(self) -> None:
        self.assertEqual(ids(sort_summaries(ALL, "seed", True)), [3, 2, 1])

    def test_unknown_column_is_an_error(self) -> None:
        with self.assertRaises(KeyError):
            sort_summaries(ALL, "colour", False)


class FilterTest(unittest.TestCase):
    def test_filter_by_mode_and_bot(self) -> None:
        self.assertEqual(
            ids(filter_summaries(ALL, ModeKind.DUEL, None)), [1, 3]
        )
        # A bot matches on either side.
        self.assertEqual(ids(filter_summaries(ALL, None, "my_bot")), [2, 3])
        self.assertEqual(
            ids(filter_summaries(ALL, ModeKind.DUEL, "my_bot")), [3]
        )
        self.assertEqual(ids(filter_summaries(ALL, None, None)), [1, 2, 3])

    def test_bot_names_are_unique_and_sorted(self) -> None:
        self.assertEqual(bot_names(ALL), ["Easy", "Hard", "Medium", "my_bot"])


if __name__ == "__main__":
    unittest.main()
