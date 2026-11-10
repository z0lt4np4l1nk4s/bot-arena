"""Tests for traps during turn resolution."""

import unittest
from dataclasses import replace

from arena.engine.turn import resolve_turn
from arena.model.actions import Action
from arena.model.geometry import Direction, Position
from arena.model.side import Side
from arena.model.state import EventKind, GameState, Trap
from arena.rules import Rules
from builders import make_state, with_player

RULES = Rules(grid_size=10)
EMPTY = "." * 10
LEFT, RIGHT = Direction.LEFT, Direction.RIGHT


def picture(*rows: str) -> GameState:
    """Build a 10x10 state; missing rows at the bottom are empty."""
    return make_state([*rows, *[EMPTY] * (10 - len(rows))], rules=RULES)


def play(
    state: GameState,
    blue: Action | None = None,
    red: Action | None = None,
    rules: Rules = RULES,
) -> GameState:
    """Resolve one turn with the given actions (``None`` means wait)."""
    actions = {}
    if blue is not None:
        actions[Side.BLUE] = blue
    if red is not None:
        actions[Side.RED] = red
    return resolve_turn(state, actions, rules)


def refusal_reasons(state: GameState) -> list[str]:
    """The reasons of all refused actions in the last turn."""
    return [
        event.reason
        for event in state.events
        if event.kind is EventKind.ACTION_REFUSED
    ]


START = picture(EMPTY, ".B......R.")


class PlaceTrapTest(unittest.TestCase):
    def test_trap_is_placed_on_a_distant_cell(self) -> None:
        after = play(START, Action.trap(Position(6, 4)))
        self.assertEqual(after.traps, (Trap(Side.BLUE, Position(6, 4), 24),))
        blue = after.player(Side.BLUE)
        self.assertEqual((blue.free_traps, blue.trap_cooldown), (2, 8))

    def test_placing_a_trap_takes_the_turn(self) -> None:
        after = play(START, Action.trap(Position(6, 4)))
        self.assertEqual(after.player(Side.BLUE).position, Position(1, 1))

    def test_refused_targets(self) -> None:
        state = picture("....#.....", ".B......R.")
        cases = [
            (Position(4, 0), "not walkable"),
            (Position(10, 3), "not walkable"),
            (Position(0, 0), "base"),
            (Position(9, 9), "base"),
            (Position(1, 1), "occupied"),
            (Position(8, 1), "occupied"),
            (Position(7, 1), "too close to opponent"),
            (Position(8, 2), "too close to opponent"),
        ]
        for target, reason in cases:
            after = play(state, Action.trap(target))
            with self.subTest(target=target):
                self.assertEqual(after.traps, ())
                self.assertEqual(refusal_reasons(after), [reason])

    def test_two_cells_from_opponent_is_allowed(self) -> None:
        after = play(START, Action.trap(Position(6, 1)))
        self.assertEqual(len(after.traps), 1)

    def test_second_trap_on_same_cell_is_refused(self) -> None:
        rules = Rules(grid_size=10, trap_cooldown=0)
        state = play(START, Action.trap(Position(6, 4)), rules=rules)
        after = play(state, Action.trap(Position(6, 4)), rules=rules)
        self.assertEqual(len(after.traps), 1)
        self.assertEqual(refusal_reasons(after), ["trap already here"])

    def test_cooldown_blocks_next_eight_turns(self) -> None:
        state = play(START, Action.trap(Position(6, 4)))
        refused = []
        for column in range(9):
            state = play(state, Action.trap(Position(column, 7)))
            refused.append(refusal_reasons(state) == ["cooldown"])
        self.assertEqual(refused, [True] * 8 + [False])

    def test_fourth_active_trap_is_refused(self) -> None:
        rules = Rules(grid_size=10, trap_cooldown=0)
        state = START
        for column in range(3):
            state = play(state, Action.trap(Position(column, 6)), rules=rules)
        self.assertEqual(len(state.traps), 3)
        after = play(state, Action.trap(Position(3, 6)), rules=rules)
        self.assertEqual(len(after.traps), 3)
        self.assertEqual(refusal_reasons(after), ["no free trap"])

    def test_default_rules_allow_three_traps_at_once(self) -> None:
        state = START
        for turn in range(19):
            action = Action.trap(Position(turn % 10, 6 + turn // 10))
            state = play(state, action)
        self.assertEqual(len(state.traps), 3)

    def test_stunned_bot_cannot_place_trap(self) -> None:
        state = with_player(START, Side.BLUE, stunned_turns=1)
        after = play(state, Action.trap(Position(6, 4)))
        self.assertEqual(after.traps, ())


class TriggerTrapTest(unittest.TestCase):
    def trapped_red(self) -> GameState:
        """Blue traps (6,1); Red walks onto it two turns later."""
        state = play(START, Action.trap(Position(6, 1)))
        state = play(state, red=Action.move(LEFT))
        return play(state, red=Action.move(LEFT))

    def test_opponent_stepping_on_trap_is_stuck_three_turns(self) -> None:
        after = self.trapped_red()
        red = after.player(Side.RED)
        self.assertEqual(red.position, Position(6, 1))
        self.assertEqual(red.trapped_turns, 3)
        self.assertIn(EventKind.TRAPPED, [e.kind for e in after.events])

    def test_triggered_trap_leaves_the_map(self) -> None:
        after = self.trapped_red()
        self.assertEqual(after.traps, ())
        self.assertEqual(len(after.spent_traps), 1)

    def test_trapped_bot_cannot_move_for_three_turns(self) -> None:
        state = self.trapped_red()
        positions = []
        for _ in range(4):
            state = play(state, red=Action.move(LEFT))
            positions.append(state.player(Side.RED).position.x)
        self.assertEqual(positions, [6, 6, 6, 5])

    def test_own_trap_does_not_affect_owner(self) -> None:
        state = play(START, Action.trap(Position(2, 1)))
        state = play(state, Action.move(RIGHT))
        blue = state.player(Side.BLUE)
        self.assertEqual(blue.position, Position(2, 1))
        self.assertEqual(blue.trapped_turns, 0)

    def test_both_bots_trapped_in_one_turn_reported_in_side_order(
        self,
    ) -> None:
        state = replace(
            picture(EMPTY, ".B...R...."),
            traps=(
                Trap(Side.RED, Position(2, 1), 5),
                Trap(Side.BLUE, Position(4, 1), 5),
            ),
        )
        after = play(state, Action.move(RIGHT), Action.move(LEFT))
        trapped = [e.side for e in after.events if e.kind is EventKind.TRAPPED]
        self.assertEqual(trapped, [Side.BLUE, Side.RED])


class TrapLifetimeTest(unittest.TestCase):
    def test_trap_expires_after_its_lifetime_and_returns(self) -> None:
        state = play(START, Action.trap(Position(6, 4)))
        for _ in range(23):
            state = play(state)
        self.assertEqual(state.traps[0].turns_left, 1)
        state = play(state)
        self.assertEqual(state.traps, ())
        self.assertEqual(state.player(Side.BLUE).free_traps, 3)

    def test_triggered_trap_returns_when_lifetime_ends(self) -> None:
        rules = Rules(grid_size=10, trap_lifetime=5)
        state = play(START, Action.trap(Position(6, 1)), rules=rules)
        state = play(state, red=Action.move(LEFT), rules=rules)
        state = play(state, red=Action.move(LEFT), rules=rules)
        state = play(state, rules=rules)
        self.assertEqual(state.player(Side.BLUE).free_traps, 2)
        state = play(state, rules=rules)
        self.assertEqual(state.player(Side.BLUE).free_traps, 3)
        self.assertEqual(state.spent_traps, ())


class CombinedEffectsTest(unittest.TestCase):
    def test_trapped_and_stunned_longer_applies(self) -> None:
        state = with_player(
            picture(EMPTY, ".B...R...."), Side.RED, trapped_turns=3
        )
        state = play(state, Action.shoot(RIGHT), Action.move(LEFT))
        self.assertEqual(state.player(Side.RED).stunned_turns, 2)
        positions = [state.player(Side.RED).position.x]
        for _ in range(3):
            state = play(state, red=Action.move(LEFT))
            positions.append(state.player(Side.RED).position.x)
        self.assertEqual(positions, [5, 5, 5, 4])


if __name__ == "__main__":
    unittest.main()
