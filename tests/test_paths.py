"""Tests for shortest-path distances on the map."""

import unittest

from arena.map_generator.paths import bfs_distances
from arena.model.geometry import Position
from arena.model.side import Side
from arena.model.state import GameMap

BASES = {Side.BLUE: Position(0, 0), Side.RED: Position(5, 5)}


def make_map(walls: set[Position]) -> GameMap:
    """Build a 6x6 map with the given walls."""
    return GameMap(6, frozenset(walls), BASES)


class BfsDistancesTest(unittest.TestCase):
    def test_start_has_distance_zero(self) -> None:
        distances = bfs_distances(make_map(set()), Position(0, 0))
        self.assertEqual(distances[Position(0, 0)], 0)

    def test_open_grid_distance_is_manhattan(self) -> None:
        distances = bfs_distances(make_map(set()), Position(0, 0))
        self.assertEqual(distances[Position(5, 5)], 10)
        self.assertEqual(len(distances), 36)

    def test_walls_force_a_detour(self) -> None:
        # A wall row at y=2 with a single gap at x=5.
        walls = {Position(x, 2) for x in range(5)}
        distances = bfs_distances(make_map(walls), Position(0, 0))
        self.assertEqual(distances[Position(0, 5)], 15)

    def test_walls_are_never_entered(self) -> None:
        walls = {Position(x, 2) for x in range(5)}
        distances = bfs_distances(make_map(walls), Position(0, 0))
        self.assertTrue(walls.isdisjoint(distances))

    def test_enclosed_cell_is_unreachable(self) -> None:
        walls = {
            Position(3, 4),
            Position(5, 4),
            Position(4, 3),
            Position(4, 5),
        }
        distances = bfs_distances(make_map(walls), Position(0, 0))
        self.assertNotIn(Position(4, 4), distances)


if __name__ == "__main__":
    unittest.main()
