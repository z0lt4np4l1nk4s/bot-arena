"""Tests for drawing a game state on the map canvas."""

import unittest
from dataclasses import replace

from arena.engine.modes import Duel
from arena.gui.formatting import shot_lines
from arena.gui.map_canvas import SIDE_COLOURS, MapCanvas
from arena.model.geometry import Position
from arena.model.side import Side
from arena.model.state import GameState, Trap
from arena.rules import DEFAULT_RULES
from gui_support import hidden_root, item_option
from recorded import record_match

RECORDED = record_match()
START = Duel().setup_map(4)


def first_state_with_a_shot() -> GameState:
    """The state after the first recorded turn with a visible bullet."""
    for record in RECORDED.turns:
        if any(cells for _, cells in shot_lines(record.state)):
            return record.state
    message = "the recorded match has no shot"
    raise AssertionError(message)


class MapCanvasTest(unittest.TestCase):
    def setUp(self) -> None:
        self.canvas = MapCanvas(hidden_root(self), DEFAULT_RULES, size=400)

    def fills(self, tag: str) -> set[str]:
        """The fill colours of all items with ``tag``."""
        return {
            item_option(self.canvas, item, "fill")
            for item in self.canvas.find_withtag(tag)
        }

    def texts(self, tag: str) -> list[str]:
        """The texts of the text items with ``tag``."""
        return [
            item_option(self.canvas, item, "text")
            for item in self.canvas.find_withtag(tag)
            if str(self.canvas.type(item)) == "text"
        ]

    def test_draws_every_wall(self) -> None:
        self.canvas.draw(START)
        self.assertEqual(
            len(self.canvas.find_withtag("wall")), len(START.map.walls)
        )

    def test_draws_both_bases_and_bots(self) -> None:
        self.canvas.draw(START)
        self.assertEqual(len(self.canvas.find_withtag("base")), 2)
        self.assertTrue(set(SIDE_COLOURS.values()) <= self.fills("bot"))

    def test_draws_traps_of_both_owners(self) -> None:
        traps = (
            Trap(Side.BLUE, Position(5, 5), 10),
            Trap(Side.RED, Position(6, 6), 10),
        )
        self.canvas.draw(replace(START, traps=traps))
        self.assertEqual(self.fills("trap"), set(SIDE_COLOURS.values()))

    def test_draws_shot_line_in_a_turn_with_a_shot(self) -> None:
        self.canvas.draw(START)
        self.assertEqual(self.canvas.find_withtag("shot"), ())
        self.canvas.draw(first_state_with_a_shot())
        self.assertNotEqual(self.canvas.find_withtag("shot"), ())

    def test_crystal_count_shown_when_several(self) -> None:
        cell = next(iter(START.crystals))
        state = replace(START, crystals={cell: 3})
        self.canvas.draw(state)
        self.assertEqual(self.texts("crystal"), ["3"])

    def test_single_crystal_has_no_count(self) -> None:
        cell = next(iter(START.crystals))
        self.canvas.draw(replace(START, crystals={cell: 1}))
        self.assertEqual(self.texts("crystal"), [])

    def test_none_shows_placeholder(self) -> None:
        self.canvas.draw(None)
        self.assertEqual(self.texts("placeholder"), ["No match yet"])
        self.assertEqual(self.canvas.find_withtag("wall"), ())


if __name__ == "__main__":
    unittest.main()
