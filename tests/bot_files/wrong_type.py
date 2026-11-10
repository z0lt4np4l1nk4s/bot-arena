"""A bot that returns a string instead of an action."""

from arena.api import BotState


class WrongTypeBot:
    name = "Wrong type"

    def decide(self, state: BotState) -> str:
        return "left"
