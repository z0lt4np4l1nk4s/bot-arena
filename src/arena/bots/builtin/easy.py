"""Easy: wanders around at random and sometimes shoots.

A good first example: it shows the shape every bot has (a ``name`` and a
``decide`` method) and how to pick only moves that are actually possible.
"""

import random

from arena.api import Action, BotState, Direction
from arena.bots.registry import register_builtin

# Chance of shooting in a turn where shooting is allowed.
SHOOT_CHANCE = 0.1


@register_builtin
class EasyBot:
    """Moves to a random free neighbouring cell each turn."""

    name = "Easy"

    def __init__(self, random_generator: random.Random | None = None) -> None:
        """Create the bot.

        Args:
            random_generator: Source of randomness; pass one with a fixed
                seed to make the bot repeat the same choices (useful in
                tests). By default a new, unseeded one is used.
        """
        self.random = random_generator or random.Random()

    def decide(self, state: BotState) -> Action:
        """Shoot now and then, otherwise take a random possible step."""
        me = state.me
        if me.shoot_cooldown == 0 and self.random.random() < SHOOT_CHANCE:
            direction = self.random.choice(list(Direction))
            return Action.shoot(direction, f"random shot {direction.name}")
        # Only directions that lead onto a walkable cell are worth trying.
        possible = [
            direction
            for direction in Direction
            if state.map.is_walkable(me.position.moved(direction))
        ]
        if not possible:
            return Action.wait("nowhere to go")
        direction = self.random.choice(possible)
        return Action.move(direction, f"wandering {direction.name}")
