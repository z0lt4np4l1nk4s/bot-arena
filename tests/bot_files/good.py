"""A bot that always moves right."""

from arena.api import Action, BotState, Direction


class GoodBot:
    name = "Good"

    def decide(self, state: BotState) -> Action:
        return Action.move(Direction.RIGHT, "going right")
