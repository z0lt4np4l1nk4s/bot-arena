"""A bot whose process dies with os._exit() in turn 1 only."""

import os

from arena.api import Action, BotState


class DyingBot:
    name = "Dying"

    def decide(self, state: BotState) -> Action:
        if state.turn == 1:
            os._exit(3)
        return Action.wait(f"alive in turn {state.turn}")
