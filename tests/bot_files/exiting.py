"""A bot that calls sys.exit() in decide."""

import sys

from arena.api import Action, BotState


class ExitingBot:
    name = "Exiting"

    def decide(self, state: BotState) -> Action:
        sys.exit("bye")
