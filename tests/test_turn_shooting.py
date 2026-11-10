"""Tests for shooting during turn resolution."""

import unittest

from arena.engine.turn import resolve_turn
from arena.model.actions import Action
from arena.model.geometry import Direction, Position
from arena.model.side import Side
from arena.model.state import EventKind, GameState
from arena.rules import Rules
from builders import make_state, with_player

RULES = Rules(grid_size=10)
EMPTY = "." * 10
UP, DOWN = Direction.UP, Direction.DOWN
LEFT, RIGHT = Direction.LEFT, Direction.RIGHT


def picture(row0: str, row1: str) -> GameState:
    """Build a 10x10 state; only the top two rows are given."""
    return make_state([row0, row1, *[EMPTY] * 8], rules=RULES)


def play(
    state: GameState,
    blue: Action | None = None,
    red: Action | None = None,
) -> GameState:
    """Resolve one turn with the given actions (``None`` means wait)."""
    actions = {}
    if blue is not None:
        actions[Side.BLUE] = blue
    if red is not None:
        actions[Side.RED] = red
    return resolve_turn(state, actions, RULES)


def kinds(state: GameState) -> list[EventKind]:
    """The kinds of the events of the last turn."""
    return [event.kind for event in state.events]


class ShootingTest(unittest.TestCase):
    def test_hit_in_straight_line(self) -> None:
        after = play(picture(EMPTY, ".B..R....."), Action.shoot(RIGHT))
        self.assertEqual(after.player(Side.RED).stunned_turns, 2)
        self.assertIn(EventKind.HIT, kinds(after))

    def test_wall_blocks_bullet(self) -> None:
        after = play(picture(EMPTY, ".B#.R....."), Action.shoot(RIGHT))
        self.assertEqual(after.player(Side.RED).stunned_turns, 0)
        self.assertNotIn(EventKind.HIT, kinds(after))

    def test_range_is_exactly_five_cells(self) -> None:
        in_range = play(picture(EMPTY, "B....R...."), Action.shoot(RIGHT))
        too_far = play(picture(EMPTY, "B.....R..."), Action.shoot(RIGHT))
        self.assertIn(EventKind.HIT, kinds(in_range))
        self.assertNotIn(EventKind.HIT, kinds(too_far))

    def test_bullet_stops_at_map_edge(self) -> None:
        after = play(picture(EMPTY, "R.......B."), Action.shoot(RIGHT))
        self.assertNotIn(EventKind.HIT, kinds(after))

    def test_hit_uses_position_after_moves(self) -> None:
        steps_in = play(
            picture("...R......", ".B........"),
            Action.shoot(RIGHT),
            Action.move(DOWN),
        )
        steps_out = play(
            picture(EMPTY, ".B.R......"),
            Action.shoot(RIGHT),
            Action.move(DOWN),
        )
        self.assertIn(EventKind.HIT, kinds(steps_in))
        self.assertNotIn(EventKind.HIT, kinds(steps_out))

    def test_shooter_does_not_move(self) -> None:
        after = play(picture(EMPTY, ".B..R....."), Action.shoot(RIGHT))
        self.assertEqual(after.player(Side.BLUE).position, Position(1, 1))

    def test_hit_drops_carried_crystals_and_stuns(self) -> None:
        state = with_player(picture(EMPTY, ".B..R....."), Side.RED, carrying=3)
        after = play(state, Action.shoot(RIGHT))
        red = after.player(Side.RED)
        self.assertEqual((red.carrying, red.stunned_turns), (0, 2))
        self.assertEqual(after.crystals, {Position(4, 1): 3})
        dropped = [
            event
            for event in after.events
            if event.kind is EventKind.CRYSTALS_DROPPED
        ]
        self.assertEqual(dropped[0].amount, 3)

    def test_hit_without_crystals_drops_nothing(self) -> None:
        after = play(picture(EMPTY, ".B..R....."), Action.shoot(RIGHT))
        self.assertNotIn(EventKind.CRYSTALS_DROPPED, kinds(after))

    def test_hit_bot_does_not_repick_dropped_crystals(self) -> None:
        state = with_player(picture(EMPTY, ".B..R....."), Side.RED, carrying=3)
        state = play(state, Action.shoot(RIGHT))
        for _ in range(3):
            state = play(state)
        self.assertEqual(state.player(Side.RED).carrying, 0)
        self.assertEqual(state.crystals, {Position(4, 1): 3})

    def test_opponent_can_take_dropped_crystals(self) -> None:
        state = with_player(picture(EMPTY, ".BR......."), Side.RED, carrying=3)
        state = play(state, Action.shoot(RIGHT))
        state = play(state)
        state = play(state)
        state = play(state, Action.move(RIGHT), Action.move(DOWN))
        self.assertEqual(state.player(Side.BLUE).carrying, 3)
        self.assertEqual(state.crystals, {})

    def test_cooldown_blocks_next_five_turns(self) -> None:
        state = play(picture(EMPTY, ".B......R."), Action.shoot(RIGHT))
        refused = []
        for _ in range(6):
            state = play(state, Action.shoot(RIGHT))
            refused.append(EventKind.ACTION_REFUSED in kinds(state))
        self.assertEqual(refused, [True, True, True, True, True, False])

    def test_cooldown_refusal_gives_reason(self) -> None:
        state = play(picture(EMPTY, ".B......R."), Action.shoot(RIGHT))
        state = play(state, Action.shoot(RIGHT))
        self.assertEqual(state.events[0].reason, "cooldown")

    def test_both_bots_shoot_each_other(self) -> None:
        after = play(
            picture(EMPTY, ".B..R....."),
            Action.shoot(RIGHT),
            Action.shoot(LEFT),
        )
        self.assertEqual(after.player(Side.BLUE).stunned_turns, 2)
        self.assertEqual(after.player(Side.RED).stunned_turns, 2)

    def test_stun_does_not_stack(self) -> None:
        state = with_player(
            picture(EMPTY, ".B..R....."), Side.RED, stunned_turns=2
        )
        after = play(state, Action.shoot(RIGHT))
        self.assertEqual(after.player(Side.RED).stunned_turns, 2)


if __name__ == "__main__":
    unittest.main()
