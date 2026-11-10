"""Tests for the public bot interface."""

import importlib
import unittest

from arena import api
from arena.api import (
    Direction,
    GameMap,
    Position,
    Side,
    distance,
    distances_from,
    next_step,
    shortest_path,
)

BASES = {Side.BLUE: Position(0, 0), Side.RED: Position(5, 5)}
OPEN_MAP = GameMap(6, frozenset(), BASES)
# A wall row at y=2 with a single gap at x=5.
WALLED_MAP = GameMap(6, frozenset(Position(x, 2) for x in range(5)), BASES)


class DistanceTest(unittest.TestCase):
    def test_distance_is_manhattan(self) -> None:
        self.assertEqual(distance(Position(1, 2), Position(4, 6)), 7)


class ShortestPathTest(unittest.TestCase):
    def test_shortest_path_on_open_grid(self) -> None:
        path = shortest_path(OPEN_MAP, Position(0, 0), Position(2, 0))
        self.assertEqual(path, (Position(1, 0), Position(2, 0)))

    def test_shortest_path_goes_around_walls(self) -> None:
        path = shortest_path(WALLED_MAP, Position(0, 0), Position(0, 5))
        self.assertEqual(len(path), 15)
        self.assertEqual(path[-1], Position(0, 5))
        self.assertTrue(WALLED_MAP.walls.isdisjoint(path))

    def test_path_to_unreachable_goal_is_empty(self) -> None:
        enclosed = GameMap(
            6,
            frozenset(
                {
                    Position(3, 4),
                    Position(5, 4),
                    Position(4, 3),
                    Position(4, 5),
                }
            ),
            BASES,
        )
        self.assertEqual(
            shortest_path(enclosed, Position(0, 0), Position(4, 4)), ()
        )

    def test_path_to_start_is_empty(self) -> None:
        self.assertEqual(
            shortest_path(OPEN_MAP, Position(2, 2), Position(2, 2)), ()
        )

    def test_shortest_path_is_cached(self) -> None:
        start, goal = Position(0, 1), Position(5, 1)
        before = shortest_path.cache_size()
        shortest_path(OPEN_MAP, start, goal)
        shortest_path(OPEN_MAP, start, goal)
        self.assertEqual(shortest_path.cache_size(), before + 1)


class DistancesFromTest(unittest.TestCase):
    def test_distances_follow_walkable_paths(self) -> None:
        distances = distances_from(WALLED_MAP, Position(0, 0))
        self.assertEqual(distances[Position(0, 5)], 15)
        self.assertNotIn(Position(0, 2), distances)

    def test_distances_are_cached(self) -> None:
        before = distances_from.cache_size()
        distances_from(OPEN_MAP, Position(3, 3))
        distances_from(OPEN_MAP, Position(3, 3))
        self.assertEqual(distances_from.cache_size(), before + 1)


class NextStepTest(unittest.TestCase):
    def test_next_step_points_along_path(self) -> None:
        self.assertIs(
            next_step(OPEN_MAP, Position(0, 0), Position(0, 3)),
            Direction.DOWN,
        )

    def test_no_step_when_already_there(self) -> None:
        self.assertIsNone(next_step(OPEN_MAP, Position(1, 1), Position(1, 1)))


class ExportsTest(unittest.TestCase):
    def test_api_exports(self) -> None:
        module = importlib.import_module("arena.api")
        for name in api.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(module, name))
        self.assertIn("Rules", api.__all__)


if __name__ == "__main__":
    unittest.main()
