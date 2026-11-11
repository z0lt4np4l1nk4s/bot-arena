"""Tests for the History tab: listing, opening and deleting matches."""

import dataclasses
import unittest
from datetime import datetime, timedelta
from unittest import mock

from arena.gui.history_tab import HistoryTab
from arena.model.side import Side
from arena.model.state import ModeKind
from arena.storage.records import RecordedMatch, SoloRecord
from arena.storage.repository import InMemoryMatchRepository
from gui_support import hidden_root
from recorded import record_match

RECORDED = record_match(turns=10)


def variant(seed: int, **changes: object) -> RecordedMatch:
    """The recorded match with another seed, time and summary fields."""
    summary = dataclasses.replace(
        RECORDED.summary,
        seed=seed,
        played_at=RECORDED.summary.played_at + timedelta(minutes=seed),
        **changes,  # type: ignore[arg-type]
    )
    return dataclasses.replace(RECORDED, summary=summary)


class HistoryTabTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryMatchRepository()
        self.repository.save_match(variant(9))
        self.repository.save_match(variant(10))
        self.repository.save_match(
            variant(
                11,
                mode=ModeKind.SOLO,
                bots={Side.BLUE: "Medium"},
                winner=None,
                delivered={Side.BLUE: 8},
                solo_turns_used=10,
            )
        )
        self.repository.save_solo_record(
            SoloRecord(11, 10, "Medium", datetime(2026, 11, 11, 12, 0))
        )
        self.opened: list[RecordedMatch] = []
        self.deleted: list[int] = []
        self.tab = HistoryTab(
            hidden_root(self),
            self.repository,
            self.opened.append,
            self.deleted.append,
        )

    def rows(self) -> tuple[str, ...]:
        return tuple(self.tab.table.get_children())

    def seeds(self) -> list[str]:
        return [self.tab.table.set(row, "seed") for row in self.rows()]

    def test_lists_all_matches_newest_first(self) -> None:
        self.assertEqual(self.seeds(), ["11", "10", "9"])

    def test_header_click_sorts_and_second_click_reverses(self) -> None:
        self.tab.sort_by("seed")
        self.assertEqual(self.seeds(), ["9", "10", "11"])
        self.tab.sort_by("seed")
        self.assertEqual(self.seeds(), ["11", "10", "9"])

    def test_filter_by_mode(self) -> None:
        self.tab.mode_combo.set("Solo")
        self.tab.refresh()
        self.assertEqual(self.seeds(), ["11"])

    def test_bot_filter_lists_every_bot(self) -> None:
        values = list(self.tab.bot_combo.cget("values"))
        self.assertEqual(values, ["All bots", "Hard", "Medium"])

    def test_double_click_opens_match(self) -> None:
        first = self.rows()[0]
        self.tab.table.selection_set(first)
        self.tab.open_selected()
        self.assertEqual(len(self.opened), 1)
        self.assertEqual(self.opened[0].summary.seed, 11)

    def test_delete_removes_selected_match(self) -> None:
        self.tab.table.selection_set(self.rows()[1])
        with mock.patch(
            "arena.gui.history_tab.messagebox.askyesno", return_value=True
        ):
            self.tab.delete_button.invoke()
        self.assertEqual(self.seeds(), ["11", "9"])
        self.assertEqual(len(self.repository.list_matches()), 2)
        self.assertEqual(self.deleted, [2])

    def test_declined_delete_keeps_the_match(self) -> None:
        self.tab.table.selection_set(self.rows()[1])
        with mock.patch(
            "arena.gui.history_tab.messagebox.askyesno", return_value=False
        ):
            self.tab.delete_button.invoke()
        self.assertEqual(len(self.repository.list_matches()), 3)
        self.assertEqual(self.deleted, [])

    def test_delete_without_selection_does_nothing(self) -> None:
        with mock.patch("arena.gui.history_tab.messagebox.askyesno") as ask:
            self.tab.delete_button.invoke()
        ask.assert_not_called()
        self.assertEqual(len(self.repository.list_matches()), 3)

    def test_open_without_selection_does_nothing(self) -> None:
        self.tab.open_selected()
        self.assertEqual(self.opened, [])

    def test_shows_solo_records(self) -> None:
        rows = self.tab.records_table.get_children()
        self.assertEqual(
            [
                tuple(
                    self.tab.records_table.set(row, column)
                    for column in ("seed", "turns", "bot", "date")
                )
                for row in rows
            ],
            [("11", "10", "Medium", "2026-11-11 12:00")],
        )


if __name__ == "__main__":
    unittest.main()
