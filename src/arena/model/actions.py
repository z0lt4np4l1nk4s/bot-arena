"""Actions a bot can return each turn (the Command pattern).

An :class:`Action` is a small immutable command object; the engine decides
how to execute it.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final

from arena.errors import InvalidActionError
from arena.model.geometry import Direction, Position

MAX_MESSAGE_LENGTH: Final = 200


class ActionKind(Enum):
    """What a bot wants to do this turn."""

    MOVE = "move"
    SHOOT = "shoot"
    TRAP = "trap"
    WAIT = "wait"


_NEEDS_DIRECTION: Final = frozenset({ActionKind.MOVE, ActionKind.SHOOT})


@dataclass(frozen=True)
class Action:
    """One bot command, with an optional message shown in the match log.

    >>> action = Action.move(Direction.UP, "going home")
    >>> action.kind, action.direction, action.message
    (<ActionKind.MOVE: 'move'>, <Direction.UP: (0, -1)>, 'going home')
    >>> Action.trap(Position(7, 3)).target
    Position(x=7, y=3)
    """

    kind: ActionKind
    direction: Direction | None = None
    message: str = ""
    target: Position | None = None

    def __post_init__(self) -> None:
        """Check that the fields fit together and shorten long messages.

        Raises:
            InvalidActionError: If a move or shot has no direction, a trap
                or wait has one, a trap has no target or another
                action has one, or the message is not a string.
        """
        needs_direction = self.kind in _NEEDS_DIRECTION
        if needs_direction and self.direction is None:
            message = f"{self.kind.value} needs a direction"
            raise InvalidActionError(message)
        if not needs_direction and self.direction is not None:
            message = f"{self.kind.value} takes no direction"
            raise InvalidActionError(message)
        needs_target = self.kind is ActionKind.TRAP
        if needs_target != (self.target is not None):
            message = (
                f"{self.kind.value} needs a target"
                if needs_target
                else f"{self.kind.value} takes no target"
            )
            raise InvalidActionError(message)
        # Typed as str, but bots are untrusted code and may pass anything.
        raw_message: object = self.message
        if not isinstance(raw_message, str):
            message = f"message must be a string, got {raw_message!r}"
            raise InvalidActionError(message)
        if len(self.message) > MAX_MESSAGE_LENGTH:
            # Frozen dataclass: setting a field is only possible this way.
            object.__setattr__(
                self, "message", self.message[:MAX_MESSAGE_LENGTH]
            )

    @classmethod
    def move(cls, direction: Direction, message: str = "") -> "Action":
        """Move one cell in ``direction``."""
        return cls(ActionKind.MOVE, direction, message)

    @classmethod
    def shoot(cls, direction: Direction, message: str = "") -> "Action":
        """Shoot a bullet in ``direction``."""
        return cls(ActionKind.SHOOT, direction, message)

    @classmethod
    def trap(cls, target: Position, message: str = "") -> "Action":
        """Place a hidden trap on ``target``, anywhere on the map."""
        return cls(ActionKind.TRAP, None, message, target)

    @classmethod
    def wait(cls, message: str = "") -> "Action":
        """Do nothing this turn."""
        return cls(ActionKind.WAIT, None, message)
