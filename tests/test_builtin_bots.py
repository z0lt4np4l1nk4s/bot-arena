"""Tests for the built-in bots and their registry.

The strength tests play 40 full matches and take a few seconds.
"""

import random
import unittest

from arena.bots.builtin.easy import EasyBot
from arena.bots.builtin.hard import HardBot
from arena.bots.builtin.medium import MediumBot
from arena.bots.registry import builtin_bots, register_builtin
from arena.engine.modes import Duel
from arena.model.actions import Action, ActionKind
from arena.model.geometry import Direction
from arena.model.side import Side
from arena.model.state import BotState, GameState
from arena.rules import Rules
from builders import make_state, with_player
from matches import play_duel, wins

RULES = Rules(grid_size=10)
EMPTY = "." * 10


def picture(*rows: str) -> GameState:
    """Build a 10x10 state; missing rows at the bottom are empty."""
    return make_state([*rows, *[EMPTY] * (10 - len(rows))], rules=RULES)


def view(state: GameState, side: Side = Side.BLUE) -> BotState:
    """What ``side`` sees in ``state``."""
    return Duel(RULES).state_for_bot(state, side)


class RegistryTest(unittest.TestCase):
    def test_three_builtins_registered(self) -> None:
        self.assertEqual(set(builtin_bots()), {"Easy", "Medium", "Hard"})

    def test_register_rejects_non_bot(self) -> None:
        class NotABot:
            pass

        with self.assertRaises(TypeError):
            register_builtin(NotABot)  # type: ignore[type-var]

    def test_register_rejects_duplicate_name(self) -> None:
        class AnotherEasy:
            name = "Easy"

            def decide(self, state: BotState) -> Action:
                return Action.wait()

        with self.assertRaises(TypeError):
            register_builtin(AnotherEasy)


class EasyBotTest(unittest.TestCase):
    def test_easy_never_moves_into_wall(self) -> None:
        state = picture("#.#.......", "#B#.......", "###.......")
        bot = EasyBot(random.Random(3))
        for _ in range(30):
            action = bot.decide(view(state))
            if action.kind is ActionKind.MOVE:
                self.assertIs(action.direction, Direction.UP)

    def test_easy_is_reproducible(self) -> None:
        state = picture(EMPTY, ".B......R.")
        first = EasyBot(random.Random(5))
        second = EasyBot(random.Random(5))
        for _ in range(20):
            self.assertEqual(
                first.decide(view(state)), second.decide(view(state))
            )

    def test_easy_can_be_created_without_arguments(self) -> None:
        self.assertEqual(EasyBot().name, "Easy")


class MediumBotTest(unittest.TestCase):
    def test_medium_heads_for_nearest_crystal(self) -> None:
        state = picture(EMPTY, ".B..*.....", *[EMPTY] * 5, ".*........")
        action = MediumBot().decide(view(state))
        self.assertEqual(action, Action.move(Direction.RIGHT, action.message))

    def test_medium_goes_home_when_full(self) -> None:
        state = with_player(
            picture(EMPTY, ".B..*....."), Side.BLUE, carrying=3
        )
        action = MediumBot().decide(view(state))
        self.assertIs(action.kind, ActionKind.MOVE)
        self.assertIn(action.direction, {Direction.UP, Direction.LEFT})
        self.assertIn("home", action.message)

    def test_medium_message_names_its_goal(self) -> None:
        state = picture(EMPTY, ".B..*.....")
        message = MediumBot().decide(view(state)).message
        self.assertEqual(message, "crystal at (4, 1), 3 steps")

    def test_medium_never_shoots_or_traps(self) -> None:
        duel = Duel()
        state = duel.setup_map(2)
        bot = MediumBot()
        while not duel.is_over(state):
            action = bot.decide(duel.state_for_bot(state, Side.BLUE))
            self.assertIn(action.kind, {ActionKind.MOVE, ActionKind.WAIT})
            state = duel.step(state, {Side.BLUE: action})


class HardBotTest(unittest.TestCase):
    def test_hard_shoots_opponent_in_line(self) -> None:
        state = picture(EMPTY, ".B..R.....", *[EMPTY] * 6, ".........*")
        action = HardBot().decide(view(state))
        self.assertEqual(action, Action.shoot(Direction.RIGHT, action.message))

    def test_hard_does_not_shoot_through_wall(self) -> None:
        state = picture(EMPTY, ".B#.R.....", *[EMPTY] * 6, ".........*")
        action = HardBot().decide(view(state))
        self.assertIsNot(action.kind, ActionKind.SHOOT)

    def test_hard_plays_a_full_match_without_errors(self) -> None:
        final = play_duel(HardBot(), MediumBot(), seed=4)
        self.assertTrue(final.is_finished)


class StrengthTest(unittest.TestCase):
    def test_medium_beats_easy(self) -> None:
        medium, easy = wins(MediumBot, EasyBot, range(10))
        self.assertGreaterEqual(medium, 16, (medium, easy))

    def test_hard_beats_medium(self) -> None:
        hard, medium = wins(HardBot, MediumBot, range(10))
        self.assertGreater(hard, medium)
        self.assertGreaterEqual(hard, 12, (hard, medium))


if __name__ == "__main__":
    unittest.main()
