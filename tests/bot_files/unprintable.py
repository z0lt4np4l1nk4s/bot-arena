"""A bot raising an exception that cannot even be printed."""

from arena.api import Action, BotState


class UnprintableError(Exception):
    def __str__(self) -> str:
        raise RuntimeError("no text")


class UnprintableBot:
    name = "Unprintable"

    def decide(self, state: BotState) -> Action:
        raise UnprintableError
