"""A bot whose decide always fails on line 10."""

from arena.api import Action, BotState


class CrashingBot:
    name = "Crashing"

    def decide(self, state: BotState) -> Action:
        return Action.wait(str(1 / 0))
