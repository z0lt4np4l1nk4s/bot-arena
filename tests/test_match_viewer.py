"""Tests for the match viewer: map, playback controls and turn log."""

import unittest
from dataclasses import replace

from arena.gui.match_viewer import MatchViewer
from arena.rules import Rules
from gui_support import hidden_root
from recorded import record_match

RECORDED = record_match(turns=30)
TURNS = len(RECORDED.turns)


class MatchViewerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = hidden_root(self)
        self.viewer = MatchViewer(self.root, Rules())

    def label(self) -> str:
        """The turn counter text."""
        return str(self.viewer.turn_label.cget("text"))

    def test_recorded_match_starts_at_turn_zero_paused(self) -> None:
        self.viewer.show_recorded(RECORDED)
        self.assertEqual(self.label(), f"Turn 0 / {TURNS}")
        self.assertFalse(self.viewer.is_live)

    def test_log_has_two_rows_per_turn(self) -> None:
        self.viewer.show_recorded(RECORDED)
        self.assertEqual(len(self.viewer.log.get_children()), 2 * TURNS)

    def test_next_button_moves_one_turn(self) -> None:
        self.viewer.show_recorded(RECORDED)
        self.viewer.next_button.invoke()
        self.assertEqual(self.label(), f"Turn 1 / {TURNS}")

    def test_selecting_a_log_row_jumps_to_its_turn(self) -> None:
        self.viewer.show_recorded(RECORDED)
        rows = self.viewer.log.get_children()
        self.viewer.log.selection_set(rows[9])  # Red's row of turn 5
        self.root.update()
        self.assertEqual(self.label(), f"Turn 5 / {TURNS}")

    def test_current_turn_rows_are_highlighted(self) -> None:
        self.viewer.show_recorded(RECORDED)
        self.viewer.next_button.invoke()
        self.viewer.next_button.invoke()
        highlighted = [
            self.viewer.log.set(item, "turn")
            for item in self.viewer.log.tag_has("current")
        ]
        self.assertEqual(highlighted, ["2", "2"])

    def test_live_turns_are_followed(self) -> None:
        self.viewer.start_live(RECORDED.summary, RECORDED.initial_state)
        for record in RECORDED.turns[:3]:
            self.viewer.add_turn(record)
        self.assertTrue(self.viewer.is_live)
        self.assertEqual(self.label(), "Turn 3 / 30")

    def test_finishing_live_match_shows_played_turns(self) -> None:
        self.viewer.start_live(RECORDED.summary, RECORDED.initial_state)
        for record in RECORDED.turns:
            self.viewer.add_turn(record)
        self.viewer.finish_live(RECORDED, match_id=7)
        self.assertFalse(self.viewer.is_live)
        self.assertEqual(self.viewer.match_id, 7)
        self.assertEqual(self.label(), f"Turn {TURNS} / {TURNS}")

    def test_recorded_match_keeps_its_id(self) -> None:
        saved = replace(RECORDED, summary=RECORDED.summary.with_id(4))
        self.viewer.show_recorded(saved)
        self.assertEqual(self.viewer.match_id, 4)

    def test_clear_shows_empty_viewer(self) -> None:
        self.viewer.show_recorded(RECORDED)
        self.viewer.clear()
        self.assertEqual(self.viewer.log.get_children(), ())
        self.assertIsNone(self.viewer.match_id)
        self.assertNotEqual(
            self.viewer.map_canvas.find_withtag("placeholder"), ()
        )


if __name__ == "__main__":
    unittest.main()
