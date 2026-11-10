"""Tests for turn resolution: counters, moves and crystals."""

import unittest

from arena.engine.turn import resolve_turn
from arena.model.actions import Action
from arena.model.geometry import Direction, Position
from arena.model.side import Side
from arena.model.state import EventKind, GameState
from arena.rules import Rules
from builders import make_state, with_crystals, with_player

RULES = Rules(grid_size=6)
EMPTY = ["......"] * 6
UP, DOWN = Direction.UP, Direction.DOWN
LEFT, RIGHT = Direction.LEFT, Direction.RIGHT


def picture(*rows: str) -> GameState:
    """Build a 6x6 state from six text rows."""
    return make_state(rows, rules=RULES)


def blue_moves(state: GameState, direction: Direction) -> GameState:
    """Resolve one turn in which only Blue moves."""
    return resolve_turn(state, {Side.BLUE: Action.move(direction)}, RULES)


class MoveTest(unittest.TestCase):
    def test_move_to_empty_cell(self) -> None:
        state = picture("......", ".B....", *EMPTY[2:])
        after = blue_moves(state, RIGHT)
        self.assertEqual(after.player(Side.BLUE).position, Position(2, 1))

    def test_move_into_wall_keeps_position(self) -> None:
        state = picture("......", ".B#...", *EMPTY[2:])
        after = blue_moves(state, RIGHT)
        self.assertEqual(after.player(Side.BLUE).position, Position(1, 1))

    def test_move_off_map_keeps_position(self) -> None:
        state = picture("......", "B.....", *EMPTY[2:])
        after = blue_moves(state, LEFT)
        self.assertEqual(after.player(Side.BLUE).position, Position(0, 1))

    def test_same_target_both_stay(self) -> None:
        state = picture("......", ".B.R..", *EMPTY[2:])
        after = resolve_turn(
            state,
            {Side.BLUE: Action.move(RIGHT), Side.RED: Action.move(LEFT)},
            RULES,
        )
        self.assertEqual(after.player(Side.BLUE).position, Position(1, 1))
        self.assertEqual(after.player(Side.RED).position, Position(3, 1))

    def test_swap_both_stay(self) -> None:
        state = picture("......", ".BR...", *EMPTY[2:])
        after = resolve_turn(
            state,
            {Side.BLUE: Action.move(RIGHT), Side.RED: Action.move(LEFT)},
            RULES,
        )
        self.assertEqual(after.player(Side.BLUE).position, Position(1, 1))
        self.assertEqual(after.player(Side.RED).position, Position(2, 1))

    def test_can_follow_opponent_that_leaves(self) -> None:
        state = picture("......", ".BR...", *EMPTY[2:])
        after = resolve_turn(
            state,
            {Side.BLUE: Action.move(RIGHT), Side.RED: Action.move(RIGHT)},
            RULES,
        )
        self.assertEqual(after.player(Side.BLUE).position, Position(2, 1))
        self.assertEqual(after.player(Side.RED).position, Position(3, 1))

    def test_cannot_follow_opponent_that_stays(self) -> None:
        state = picture("......", "..BR#.", *EMPTY[2:])
        after = resolve_turn(
            state,
            {Side.BLUE: Action.move(RIGHT), Side.RED: Action.move(RIGHT)},
            RULES,
        )
        self.assertEqual(after.player(Side.BLUE).position, Position(2, 1))
        self.assertEqual(after.player(Side.RED).position, Position(3, 1))

    def test_cannot_enter_cell_of_waiting_opponent(self) -> None:
        state = picture("......", ".BR...", *EMPTY[2:])
        after = blue_moves(state, RIGHT)
        self.assertEqual(after.player(Side.BLUE).position, Position(1, 1))

    def test_missing_action_means_wait(self) -> None:
        state = picture("......", ".BR...", *EMPTY[2:])
        after = resolve_turn(state, {}, RULES)
        self.assertEqual(after.players, state.players)

    def test_turn_number_increases(self) -> None:
        state = picture("......", ".B....", *EMPTY[2:])
        self.assertEqual(blue_moves(state, RIGHT).turn, 1)


class CrystalTest(unittest.TestCase):
    def test_picks_up_crystals_up_to_capacity(self) -> None:
        state = picture("......", ".B5...", *EMPTY[2:])
        after = blue_moves(state, RIGHT)
        self.assertEqual(after.player(Side.BLUE).carrying, 3)
        self.assertEqual(after.crystals, {Position(2, 1): 2})

    def test_picking_up_last_crystal_clears_the_cell(self) -> None:
        state = picture("......", ".B*...", *EMPTY[2:])
        after = blue_moves(state, RIGHT)
        self.assertEqual(after.crystals, {})

    def test_full_bot_leaves_crystals(self) -> None:
        state = with_player(
            picture("......", ".B*...", *EMPTY[2:]), Side.BLUE, carrying=3
        )
        after = blue_moves(state, RIGHT)
        self.assertEqual(after.player(Side.BLUE).carrying, 3)
        self.assertEqual(after.crystals, {Position(2, 1): 1})

    def test_delivery_on_arrival_at_base(self) -> None:
        state = with_player(
            picture(".B....", *EMPTY[1:]), Side.BLUE, carrying=2
        )
        after = blue_moves(state, LEFT)
        blue = after.player(Side.BLUE)
        self.assertEqual((blue.carrying, blue.delivered), (0, 2))
        self.assertIn(EventKind.DELIVERED, [e.kind for e in after.events])
        self.assertEqual(after.events[0].amount, 2)

    def test_no_delivery_at_opponent_base(self) -> None:
        state = with_player(
            picture("R.....", *EMPTY[1:5], "....B."), Side.BLUE, carrying=2
        )
        after = blue_moves(state, RIGHT)
        blue = after.player(Side.BLUE)
        self.assertEqual((blue.carrying, blue.delivered), (2, 0))


class DisabledBotTest(unittest.TestCase):
    def test_disabled_bot_ignores_action_and_counter_drops(self) -> None:
        state = with_player(
            picture("......", ".B....", *EMPTY[2:]),
            Side.BLUE,
            stunned_turns=2,
        )
        after = blue_moves(state, RIGHT)
        blue = after.player(Side.BLUE)
        self.assertEqual(blue.position, Position(1, 1))
        self.assertEqual(blue.stunned_turns, 1)

    def test_stunned_two_turns_skips_exactly_two_turns(self) -> None:
        state = with_player(
            picture("......", ".B....", *EMPTY[2:]),
            Side.BLUE,
            stunned_turns=2,
        )
        positions = []
        for _ in range(3):
            state = blue_moves(state, RIGHT)
            positions.append(state.player(Side.BLUE).position.x)
        self.assertEqual(positions, [1, 1, 2])

    def test_disabled_bot_does_not_pick_up(self) -> None:
        state = with_player(
            picture("......", ".B....", *EMPTY[2:]),
            Side.BLUE,
            trapped_turns=1,
        )
        state = with_crystals(state, {Position(1, 1): 2})
        after = resolve_turn(state, {}, RULES)
        self.assertEqual(after.player(Side.BLUE).carrying, 0)
        self.assertEqual(after.crystals, {Position(1, 1): 2})

    def test_standing_bot_does_not_pick_up_crystals_under_it(self) -> None:
        state = with_crystals(
            picture("......", ".B....", *EMPTY[2:]), {Position(1, 1): 2}
        )
        after = resolve_turn(state, {}, RULES)
        self.assertEqual(after.player(Side.BLUE).carrying, 0)
        self.assertEqual(after.crystals, {Position(1, 1): 2})

    def test_bot_on_base_delivers_without_moving(self) -> None:
        state = with_player(
            picture("B.....", *EMPTY[1:]), Side.BLUE, carrying=1
        )
        after = resolve_turn(state, {}, RULES)
        self.assertEqual(after.player(Side.BLUE).delivered, 1)


if __name__ == "__main__":
    unittest.main()
