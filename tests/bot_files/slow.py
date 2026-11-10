"""A bot that thinks for 0.4 seconds every turn."""

import time

from arena.api import Action, BotState


class SlowBot:
    name = "Slow"

    def decide(self, state: BotState) -> Action:
        time.sleep(0.4)
        return Action.wait(f"answer for turn {state.turn}")
