"""The ``Bot`` protocol: what a class must look like to play.

A bot does not inherit from anything; any class with a ``name`` and a
``decide`` method fits (structural typing).
"""

from typing import Protocol, runtime_checkable

from arena.model.actions import Action
from arena.model.state import BotState


@runtime_checkable
class Bot(Protocol):
    """A player: gets the game state each turn and returns one action."""

    name: str

    def decide(self, state: BotState) -> Action:
        """Choose this turn's action."""
        ...
