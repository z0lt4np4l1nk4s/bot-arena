"""Tests for the fair map generator."""

import unittest

from arena.errors import MapGenerationError
from arena.map_generator.generator import generate, solo_crystals
from arena.map_generator.paths import bfs_distances
from arena.model.geometry import Position
from arena.model.side import Side
from arena.rules import Rules

RULES = Rules()
SEEDS = range(20)


class GenerateTest(unittest.TestCase):
    def test_same_seed_gives_same_map(self) -> None:
        self.assertEqual(generate(42, RULES), generate(42, RULES))

    def test_different_seeds_give_different_maps(self) -> None:
        self.assertNotEqual(
            generate(1, RULES)[0].walls, generate(2, RULES)[0].walls
        )

    def test_bases_are_in_opposite_corners(self) -> None:
        game_map, _ = generate(0, RULES)
        self.assertEqual(game_map.base_of(Side.BLUE), Position(0, 0))
        self.assertEqual(game_map.base_of(Side.RED), Position(19, 19))

    def test_map_is_rotationally_symmetric(self) -> None:
        for seed in SEEDS:
            game_map, crystals = generate(seed, RULES)
            with self.subTest(seed=seed):
                for wall in game_map.walls:
                    self.assertIn(wall.rotated(20), game_map.walls)
                for cell in crystals:
                    self.assertIn(cell.rotated(20), crystals)

    def test_counts_match_rules(self) -> None:
        game_map, crystals = generate(7, RULES)
        self.assertEqual(len(game_map.walls), 60)  # 15 % of 400 cells
        self.assertEqual(sum(crystals.values()), 16)
        self.assertEqual(set(crystals.values()), {1})

    def test_bases_and_their_neighbours_are_free(self) -> None:
        protected = [
            Position(0, 0),
            Position(1, 0),
            Position(0, 1),
            Position(1, 1),
            Position(19, 19),
            Position(18, 19),
            Position(19, 18),
            Position(18, 18),
        ]
        for seed in SEEDS:
            game_map, crystals = generate(seed, RULES)
            with self.subTest(seed=seed):
                for cell in protected:
                    self.assertNotIn(cell, game_map.walls)
                self.assertNotIn(Position(0, 0), crystals)
                self.assertNotIn(Position(19, 19), crystals)

    def test_crystals_are_never_on_walls(self) -> None:
        for seed in SEEDS:
            game_map, crystals = generate(seed, RULES)
            with self.subTest(seed=seed):
                self.assertTrue(game_map.walls.isdisjoint(crystals))

    def test_every_crystal_reachable_from_both_bases(self) -> None:
        for seed in SEEDS:
            game_map, crystals = generate(seed, RULES)
            for side in Side:
                reachable = bfs_distances(game_map, game_map.base_of(side))
                with self.subTest(seed=seed, side=side):
                    self.assertTrue(set(crystals) <= set(reachable))

    def test_both_bases_have_equal_path_lengths(self) -> None:
        for seed in SEEDS:
            game_map, crystals = generate(seed, RULES)
            blue = bfs_distances(game_map, game_map.base_of(Side.BLUE))
            red = bfs_distances(game_map, game_map.base_of(Side.RED))
            with self.subTest(seed=seed):
                self.assertEqual(
                    sorted(blue[cell] for cell in crystals),
                    sorted(red[cell] for cell in crystals),
                )

    def test_impossible_rules_raise(self) -> None:
        with self.assertRaises(MapGenerationError):
            generate(0, Rules(grid_size=6, crystal_pairs=40))


class SoloCrystalsTest(unittest.TestCase):
    def test_keeps_exactly_eight_crystals_on_blue_half(self) -> None:
        for seed in SEEDS:
            game_map, crystals = generate(seed, RULES)
            solo = solo_crystals(game_map, crystals)
            with self.subTest(seed=seed):
                self.assertEqual(sum(solo.values()), 8)
                for cell in solo:
                    self.assertLess(cell.x + cell.y, 19)


if __name__ == "__main__":
    unittest.main()
