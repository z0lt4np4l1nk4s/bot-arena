"""A bot that never answers in turn 1 and answers normally otherwise."""

from arena.api import Action, BotState


class HangingBot:
    name = "Hanging"

    def decide(self, state: BotState) -> Action:
        while state.turn == 1:
            pass
        return Action.wait(f"awake in turn {state.turn}")
