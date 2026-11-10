"""Tests for the map, player state and game state."""

import unittest
from dataclasses import replace

from arena.model.geometry import Position
from arena.model.side import Side
from arena.model.state import (
    GameMap,
    GameState,
    ModeKind,
    OpponentView,
    PlayerState,
)

BASES = {Side.BLUE: Position(0, 0), Side.RED: Position(5, 5)}
SMALL_MAP = GameMap(6, frozenset({Position(2, 2)}), BASES)


def make_game_state(
    *,
    crystals: dict[Position, int] | None = None,
    blue_carrying: int = 0,
    turn: int = 0,
    max_turns: int = 200,
) -> GameState:
    """Build a small duel state with one crystal by default."""
    return GameState(
        mode=ModeKind.DUEL,
        turn=turn,
        max_turns=max_turns,
        map=SMALL_MAP,
        crystals={Position(1, 1): 1} if crystals is None else crystals,
        players={
            Side.BLUE: PlayerState(
                Side.BLUE, Position(0, 0), carrying=blue_carrying
            ),
            Side.RED: PlayerState(Side.RED, Position(5, 5)),
        },
    )


class GameMapTest(unittest.TestCase):
    def test_walls_and_outside_are_not_walkable(self) -> None:
        self.assertFalse(SMALL_MAP.is_walkable(Position(2, 2)))
        self.assertFalse(SMALL_MAP.is_walkable(Position(6, 0)))
        self.assertTrue(SMALL_MAP.is_walkable(Position(1, 1)))

    def test_base_of_each_side(self) -> None:
        self.assertEqual(SMALL_MAP.base_of(Side.RED), Position(5, 5))


class PlayerStateTest(unittest.TestCase):
    def test_player_is_disabled_when_stunned_or_trapped(self) -> None:
        player = PlayerState(Side.BLUE, Position(0, 0))
        self.assertFalse(player.is_disabled)
        self.assertTrue(replace(player, stunned_turns=1).is_disabled)
        self.assertTrue(replace(player, trapped_turns=2).is_disabled)

    def test_opponent_view_copies_public_fields(self) -> None:
        player = PlayerState(
            Side.RED, Position(4, 4), carrying=2, delivered=5, free_traps=2
        )
        view = OpponentView.of(player)
        self.assertEqual(
            (view.side, view.position, view.carrying, view.delivered),
            (Side.RED, Position(4, 4), 2, 5),
        )

    def test_opponent_view_hides_free_traps(self) -> None:
        view = OpponentView.of(
            PlayerState(Side.RED, Position(5, 5), free_traps=2)
        )
        self.assertFalse(hasattr(view, "free_traps"))


class GameStateTest(unittest.TestCase):
    def test_crystals_left_counts_ground_and_carried(self) -> None:
        state = make_game_state(crystals={Position(1, 1): 2}, blue_carrying=1)
        self.assertEqual(state.crystals_left, 3)

    def test_finished_when_turn_limit_reached(self) -> None:
        self.assertTrue(make_game_state(turn=200, max_turns=200).is_finished)

    def test_finished_when_no_crystals_left(self) -> None:
        self.assertTrue(make_game_state(crystals={}).is_finished)

    def test_not_finished_during_play(self) -> None:
        self.assertFalse(make_game_state(turn=10).is_finished)

    def test_player_lookup(self) -> None:
        state = make_game_state(blue_carrying=2)
        self.assertEqual(state.player(Side.BLUE).carrying, 2)


if __name__ == "__main__":
    unittest.main()
