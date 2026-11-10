"""Tests for sides and bot actions."""

import unittest

from arena.errors import InvalidActionError
from arena.model.actions import MAX_MESSAGE_LENGTH, Action, ActionKind
from arena.model.geometry import Direction, Position
from arena.model.side import Side


class SideTest(unittest.TestCase):
    def test_opponent_of_each_side(self) -> None:
        self.assertIs(Side.BLUE.opponent, Side.RED)
        self.assertIs(Side.RED.opponent, Side.BLUE)


class ActionTest(unittest.TestCase):
    def test_factories_build_matching_kind(self) -> None:
        self.assertEqual(Action.move(Direction.UP).kind, ActionKind.MOVE)
        self.assertEqual(
            Action.shoot(Direction.LEFT).direction, Direction.LEFT
        )
        self.assertEqual(Action.trap(Position(3, 4)).target, Position(3, 4))
        self.assertEqual(Action.wait("idle").message, "idle")

    def test_move_without_direction_is_invalid(self) -> None:
        with self.assertRaises(InvalidActionError):
            Action(ActionKind.MOVE)

    def test_shoot_without_direction_is_invalid(self) -> None:
        with self.assertRaises(InvalidActionError):
            Action(ActionKind.SHOOT)

    def test_wait_with_direction_is_invalid(self) -> None:
        with self.assertRaises(InvalidActionError):
            Action(ActionKind.WAIT, Direction.UP)

    def test_trap_with_direction_is_invalid(self) -> None:
        with self.assertRaises(InvalidActionError):
            Action(ActionKind.TRAP, Direction.UP, target=Position(1, 1))

    def test_trap_without_target_is_invalid(self) -> None:
        with self.assertRaises(InvalidActionError):
            Action(ActionKind.TRAP)

    def test_move_with_target_is_invalid(self) -> None:
        with self.assertRaises(InvalidActionError):
            Action(ActionKind.MOVE, Direction.UP, target=Position(1, 1))

    def test_non_string_message_is_invalid(self) -> None:
        with self.assertRaises(InvalidActionError):
            # Wrong type on purpose: bots are untrusted user code.
            Action.wait(42)  # type: ignore[arg-type]

    def test_long_message_is_truncated(self) -> None:
        message = Action.wait("x" * 500).message
        self.assertEqual(len(message), MAX_MESSAGE_LENGTH)
        self.assertEqual(MAX_MESSAGE_LENGTH, 200)

    def test_actions_are_immutable_values(self) -> None:
        self.assertEqual(Action.move(Direction.UP), Action.move(Direction.UP))


if __name__ == "__main__":
    unittest.main()
