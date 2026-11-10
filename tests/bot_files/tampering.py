"""A bot returning tampered actions, chosen by the turn number."""

from arena.api import Action, BotState, Direction
from arena.model.actions import ActionKind


class FancyAction(Action):
    pass


class TamperingBot:
    name = "Tampering"

    def decide(self, state: BotState) -> Action:
        if state.turn == 1:
            return FancyAction(ActionKind.MOVE, Direction.UP, "fancy")
        if state.turn == 2:
            action = Action.wait()
            object.__setattr__(action, "message", "y" * 5000)
            return action
        # A move whose direction is not a Direction.
        bad = Action.move(Direction.UP)
        object.__setattr__(bad, "direction", "garbage")
        return bad
