"""The two sides of a match."""

from enum import Enum


class Side(Enum):
    """A player's side; Blue starts top-left, Red bottom-right.

    >>> Side.BLUE.opponent
    <Side.RED: 'red'>
    """

    BLUE = "blue"
    RED = "red"

    @property
    def opponent(self) -> "Side":
        """The other side."""
        return Side.RED if self is Side.BLUE else Side.BLUE
