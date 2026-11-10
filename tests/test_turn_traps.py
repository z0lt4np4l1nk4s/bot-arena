"""Tests for traps during turn resolution."""

import unittest

from arena.engine.turn import resolve_turn
from arena.model.actions import Action
from arena.model.geometry import Direction, Position
from arena.model.side import Side
from arena.model.state import EventKind, GameState, Trap
from arena.rules import Rules
from builders import make_state, with_player

RULES = Rules(grid_size=6)
EMPTY = "......"
LEFT, RIGHT = Direction.LEFT, Direction.RIGHT


def picture(row0: str, row1: str) -> GameState:
    """Build a 6x6 state; only the top two rows are given."""
    return make_state([row0, row1, *[EMPTY] * 4], rules=RULES)


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


def refusal_reasons(state: GameState) -> list[str]:
    """The reasons of all refused actions in the last turn."""
    return [
        event.reason
        for event in state.events
        if event.kind is EventKind.ACTION_REFUSED
    ]


class PlaceTrapTest(unittest.TestCase):
    def test_place_trap_uses_a_free_trap(self) -> None:
        after = play(picture(EMPTY, "..B..R"), Action.trap())
        self.assertEqual(after.traps, (Trap(Side.BLUE, Position(2, 1), 4),))
        self.assertEqual(after.player(Side.BLUE).free_traps, 2)

    def test_fourth_active_trap_is_refused(self) -> None:
        state = with_player(picture(EMPTY, "..B..R"), Side.BLUE, free_traps=0)
        after = play(state, Action.trap())
        self.assertEqual(after.traps, ())
        self.assertEqual(refusal_reasons(after), ["no free trap"])

    def test_trap_on_base_is_refused(self) -> None:
        after = play(picture("B.....", ".....R"), Action.trap())
        self.assertEqual(after.traps, ())
        self.assertEqual(refusal_reasons(after), ["base"])

    def test_second_trap_on_same_cell_is_refused(self) -> None:
        state = play(picture(EMPTY, "..B..R"), Action.trap())
        after = play(state, Action.trap())
        self.assertEqual(len(after.traps), 1)
        self.assertEqual(refusal_reasons(after), ["trap already here"])

    def test_stunned_bot_cannot_place_trap(self) -> None:
        state = with_player(
            picture(EMPTY, "..B..R"), Side.BLUE, stunned_turns=1
        )
        after = play(state, Action.trap())
        self.assertEqual(after.traps, ())


class TriggerTrapTest(unittest.TestCase):
    def trapped_red(self) -> GameState:
        """Blue traps (2,1), then steps away while Red follows onto it."""
        state = play(picture(EMPTY, "..BR.."), Action.trap())
        return play(state, Action.move(LEFT), Action.move(LEFT))

    def test_opponent_stepping_on_trap_is_stuck_three_turns(self) -> None:
        after = self.trapped_red()
        red = after.player(Side.RED)
        self.assertEqual(red.position, Position(2, 1))
        self.assertEqual(red.trapped_turns, 3)
        self.assertIn(EventKind.TRAPPED, [e.kind for e in after.events])

    def test_triggered_trap_leaves_the_map(self) -> None:
        after = self.trapped_red()
        self.assertEqual(after.traps, ())
        self.assertEqual(len(after.spent_traps), 1)

    def test_own_trap_does_not_affect_owner(self) -> None:
        state = play(picture(EMPTY, "..B..R"), Action.trap())
        state = play(state, Action.move(RIGHT))
        state = play(state, Action.move(LEFT))
        blue = state.player(Side.BLUE)
        self.assertEqual(blue.position, Position(2, 1))
        self.assertEqual(blue.trapped_turns, 0)

    def test_trapped_bot_cannot_move_for_three_turns(self) -> None:
        state = self.trapped_red()
        positions = []
        for _ in range(4):
            state = play(state, red=Action.move(RIGHT))
            positions.append(state.player(Side.RED).position.x)
        self.assertEqual(positions, [2, 2, 2, 3])


class TrapLifetimeTest(unittest.TestCase):
    def test_trap_expires_after_five_turns_and_returns(self) -> None:
        state = play(picture(EMPTY, "..B..R"), Action.trap())
        for _ in range(3):
            state = play(state)
        self.assertEqual(state.traps[0].turns_left, 1)
        state = play(state)
        self.assertEqual(state.traps, ())
        self.assertEqual(state.player(Side.BLUE).free_traps, 3)

    def test_triggered_trap_returns_when_lifetime_ends(self) -> None:
        state = play(picture(EMPTY, "..BR.."), Action.trap())
        state = play(state, Action.move(LEFT), Action.move(LEFT))
        for _ in range(2):
            state = play(state)
        self.assertEqual(state.player(Side.BLUE).free_traps, 2)
        state = play(state)
        self.assertEqual(state.player(Side.BLUE).free_traps, 3)
        self.assertEqual(state.spent_traps, ())


class CombinedEffectsTest(unittest.TestCase):
    def test_trapped_and_stunned_longer_applies(self) -> None:
        state = with_player(
            picture(EMPTY, ".B...R"), Side.RED, trapped_turns=3
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
