"""Tests for the game modes (Duel and Solo)."""

import unittest
from dataclasses import replace

from arena.engine.modes import Duel, GameMode, Solo
from arena.model.actions import Action
from arena.model.geometry import Direction, Position
from arena.model.side import Side
from arena.model.state import (
    EventKind,
    GameState,
    ModeKind,
    OpponentView,
)
from arena.rules import Rules
from builders import with_player


def free_cell(state: GameState) -> Position:
    """A walkable cell away from both bots: the crystal nearest Blue."""
    return min(state.crystals, key=lambda cell: cell.x + cell.y)


class RegistryTest(unittest.TestCase):
    def test_create_returns_registered_mode(self) -> None:
        self.assertIsInstance(GameMode.create(ModeKind.DUEL), Duel)
        self.assertIsInstance(GameMode.create(ModeKind.SOLO), Solo)

    def test_base_class_cannot_be_instantiated(self) -> None:
        with self.assertRaises(TypeError):
            GameMode()  # type: ignore[abstract]


class SetupTest(unittest.TestCase):
    def test_duel_setup(self) -> None:
        state = Duel().setup_map(5)
        self.assertEqual(state.mode, ModeKind.DUEL)
        self.assertEqual(state.player(Side.BLUE).position, Position(0, 0))
        self.assertEqual(state.player(Side.RED).position, Position(19, 19))
        self.assertEqual(state.player(Side.RED).free_traps, 3)
        self.assertEqual(
            (state.turn, state.max_turns, state.crystals_left), (0, 200, 16)
        )

    def test_solo_setup(self) -> None:
        state = Solo().setup_map(5)
        self.assertEqual(state.mode, ModeKind.SOLO)
        self.assertEqual(set(state.players), {Side.BLUE})
        self.assertEqual((state.max_turns, state.crystals_left), (300, 8))

    def test_same_seed_same_start(self) -> None:
        self.assertEqual(Duel().setup_map(9), Duel().setup_map(9))


class BotViewTest(unittest.TestCase):
    def test_bot_sees_own_traps_but_not_opponents(self) -> None:
        duel = Duel()
        state = duel.setup_map(1)
        state = duel.step(state, {Side.BLUE: Action.move(Direction.RIGHT)})
        state = duel.step(state, {Side.BLUE: Action.trap(free_cell(state))})
        blue_view = duel.state_for_bot(state, Side.BLUE)
        red_view = duel.state_for_bot(state, Side.RED)
        self.assertEqual(len(blue_view.my_traps), 1)
        self.assertEqual(red_view.my_traps, ())
        self.assertIsInstance(red_view.opponent, OpponentView)

    def test_bot_view_carries_the_rules(self) -> None:
        duel = Duel(Rules(bullet_range=7))
        view = duel.state_for_bot(duel.setup_map(1), Side.BLUE)
        self.assertEqual(view.rules.bullet_range, 7)

    def test_view_carries_turn_and_map(self) -> None:
        duel = Duel()
        state = duel.setup_map(1)
        view = duel.state_for_bot(state, Side.RED)
        self.assertEqual((view.turn, view.max_turns), (0, 200))
        self.assertEqual(view.map, state.map)
        self.assertEqual(view.me, state.player(Side.RED))

    def test_opponent_refusals_are_hidden(self) -> None:
        duel = Duel()
        state = duel.setup_map(1)
        state = duel.step(state, {Side.BLUE: Action.move(Direction.RIGHT)})
        state = duel.step(state, {Side.BLUE: Action.trap(free_cell(state))})
        state = duel.step(state, {Side.BLUE: Action.trap(free_cell(state))})
        blue_view = duel.state_for_bot(state, Side.BLUE)
        red_view = duel.state_for_bot(state, Side.RED)
        self.assertEqual(len(blue_view.events), 1)
        self.assertEqual(red_view.events, ())

    def test_changing_the_view_does_not_change_the_game(self) -> None:
        duel = Duel()
        state = duel.setup_map(1)
        view = duel.state_for_bot(state, Side.BLUE)
        view.crystals.clear()  # type: ignore[attr-defined]
        self.assertEqual(state.crystals_left, 16)

    def test_solo_bot_has_no_opponent(self) -> None:
        solo = Solo()
        state = solo.setup_map(1)
        self.assertIsNone(solo.state_for_bot(state, Side.BLUE).opponent)


class StepTest(unittest.TestCase):
    def test_step_advances_the_turn(self) -> None:
        duel = Duel()
        self.assertEqual(duel.step(duel.setup_map(1), {}).turn, 1)

    def test_solo_refuses_shoot_and_trap(self) -> None:
        solo = Solo()
        state = solo.setup_map(1)
        for action in [
            Action.shoot(Direction.RIGHT),
            Action.trap(free_cell(state)),
        ]:
            after = solo.step(state, {Side.BLUE: action})
            with self.subTest(action=action.kind):
                self.assertEqual(after.traps, ())
                self.assertEqual(after.player(Side.BLUE).shoot_cooldown, 0)
                self.assertEqual(
                    after.events[0].kind, EventKind.ACTION_REFUSED
                )
                self.assertEqual(after.events[0].reason, "not allowed in solo")


class ResultTest(unittest.TestCase):
    def test_duel_winner_has_more_delivered(self) -> None:
        duel = Duel()
        state = with_player(duel.setup_map(1), Side.RED, delivered=5)
        self.assertIs(duel.winner(state), Side.RED)

    def test_duel_draw_has_no_winner(self) -> None:
        duel = Duel()
        state = with_player(duel.setup_map(1), Side.RED, delivered=4)
        state = with_player(state, Side.BLUE, delivered=4)
        self.assertIsNone(duel.winner(state))

    def test_duel_ends_at_turn_200(self) -> None:
        duel = Duel()
        state = duel.setup_map(1)
        self.assertFalse(duel.is_over(replace(state, turn=199)))
        self.assertTrue(duel.is_over(replace(state, turn=200)))

    def test_solo_turns_used_when_all_delivered(self) -> None:
        solo = Solo()
        state = replace(solo.setup_map(1), crystals={}, turn=57)
        self.assertEqual(solo.turns_used(state), 57)
        self.assertIs(solo.winner(state), Side.BLUE)

    def test_solo_not_finished_returns_none(self) -> None:
        solo = Solo()
        state = replace(solo.setup_map(1), turn=300)
        self.assertIsNone(solo.turns_used(state))
        self.assertIsNone(solo.winner(state))


if __name__ == "__main__":
    unittest.main()
