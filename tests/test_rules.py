"""Tests for the game rules configuration."""

import unittest

from arena.errors import RulesError
from arena.rules import DEFAULT_RULES, Bounded, Rules


class RulesTest(unittest.TestCase):
    def test_defaults_match_spec(self) -> None:
        rules = Rules()
        self.assertEqual(
            (
                rules.grid_size,
                rules.wall_percent,
                rules.crystal_pairs,
                rules.carry_capacity,
                rules.bullet_range,
                rules.shoot_cooldown,
                rules.stun_turns,
                rules.traps_per_bot,
                rules.trap_lifetime,
                rules.trap_stuck_turns,
                rules.duel_max_turns,
                rules.solo_max_turns,
                rules.turn_time_limit_ms,
                rules.bot_kill_timeout_ms,
            ),
            (20, 15, 8, 3, 5, 5, 2, 3, 5, 3, 200, 300, 100, 2000),
        )

    def test_default_rules_instance_uses_defaults(self) -> None:
        self.assertEqual(DEFAULT_RULES.grid_size, 20)

    def test_override_within_bounds(self) -> None:
        self.assertEqual(Rules(bullet_range=7).bullet_range, 7)

    def test_override_does_not_change_other_instances(self) -> None:
        Rules(bullet_range=7)
        self.assertEqual(Rules().bullet_range, 5)

    def test_value_outside_bounds_is_rejected(self) -> None:
        for name, value in [("bullet_range", 0), ("wall_percent", 41)]:
            with self.subTest(name=name), self.assertRaises(RulesError):
                Rules(**{name: value})

    def test_bounds_themselves_are_accepted(self) -> None:
        for name, value in [
            ("bullet_range", 1),
            ("bullet_range", 20),
            ("wall_percent", 0),
        ]:
            with self.subTest(name=name, value=value):
                self.assertEqual(getattr(Rules(**{name: value}), name), value)

    def test_non_integer_is_rejected(self) -> None:
        for value in [True, 3.0, "5"]:
            with self.subTest(value=value), self.assertRaises(RulesError):
                # Wrong types on purpose: this checks runtime validation.
                Rules(carry_capacity=value)  # type: ignore[arg-type]

    def test_rules_cannot_be_unfrozen_by_deleting(self) -> None:
        rules = Rules()
        with self.assertRaises(RulesError):
            del rules._frozen

    def test_odd_grid_size_is_rejected(self) -> None:
        with self.assertRaises(RulesError):
            Rules(grid_size=7)

    def test_unknown_rule_is_rejected(self) -> None:
        with self.assertRaises(RulesError):
            Rules(bullet_speed=3)

    def test_rules_are_frozen_after_creation(self) -> None:
        rules = Rules()
        with self.assertRaises(RulesError):
            rules.bullet_range = 3


class BoundedTest(unittest.TestCase):
    def test_unset_value_reads_as_default(self) -> None:
        class Example:
            speed = Bounded(default=3, minimum=1, maximum=5)

        self.assertEqual(Example().speed, 3)

    def test_default_outside_range_is_rejected(self) -> None:
        with self.assertRaises(RulesError):
            Bounded(default=9, minimum=1, maximum=5)

    def test_minimum_above_maximum_is_rejected(self) -> None:
        with self.assertRaises(RulesError):
            Bounded(default=3, minimum=5, maximum=1)


if __name__ == "__main__":
    unittest.main()
