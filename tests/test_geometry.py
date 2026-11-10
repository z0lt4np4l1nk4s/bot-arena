"""Tests for grid positions and directions."""

import unittest

from arena.model.geometry import Direction, Position, manhattan


class DirectionTest(unittest.TestCase):
    def test_up_decreases_row(self) -> None:
        self.assertEqual((Direction.UP.dx, Direction.UP.dy), (0, -1))

    def test_right_increases_column(self) -> None:
        self.assertEqual((Direction.RIGHT.dx, Direction.RIGHT.dy), (1, 0))

    def test_opposite_of_each_direction(self) -> None:
        pairs = {
            Direction.UP: Direction.DOWN,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
            Direction.RIGHT: Direction.LEFT,
        }
        for direction, expected in pairs.items():
            with self.subTest(direction=direction):
                self.assertIs(direction.opposite, expected)


class PositionTest(unittest.TestCase):
    def test_moved_returns_neighbour_in_direction(self) -> None:
        self.assertEqual(Position(5, 5).moved(Direction.LEFT), Position(4, 5))

    def test_moved_does_not_change_original(self) -> None:
        start = Position(2, 3)
        start.moved(Direction.DOWN)
        self.assertEqual(start, Position(2, 3))

    def test_positions_are_hashable(self) -> None:
        self.assertEqual(len({Position(1, 1), Position(1, 1)}), 1)

    def test_is_inside_grid(self) -> None:
        self.assertTrue(Position(0, 0).is_inside(20))
        self.assertTrue(Position(19, 19).is_inside(20))
        self.assertFalse(Position(20, 0).is_inside(20))
        self.assertFalse(Position(0, -1).is_inside(20))

    def test_rotated_maps_corner_to_opposite_corner(self) -> None:
        self.assertEqual(Position(0, 0).rotated(20), Position(19, 19))

    def test_rotating_twice_returns_original(self) -> None:
        position = Position(3, 14)
        self.assertEqual(position.rotated(20).rotated(20), position)

    def test_no_cell_maps_to_itself_on_even_grid(self) -> None:
        size = 20
        for x in range(size):
            for y in range(size):
                with self.subTest(x=x, y=y):
                    position = Position(x, y)
                    self.assertNotEqual(position.rotated(size), position)


class ManhattanTest(unittest.TestCase):
    def test_distance_is_sum_of_axis_differences(self) -> None:
        self.assertEqual(manhattan(Position(1, 2), Position(4, 6)), 7)

    def test_distance_is_symmetric(self) -> None:
        a, b = Position(0, 9), Position(7, 3)
        self.assertEqual(manhattan(a, b), manhattan(b, a))


if __name__ == "__main__":
    unittest.main()
