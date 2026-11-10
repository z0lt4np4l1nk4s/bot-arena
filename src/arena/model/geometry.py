"""Grid geometry: positions on the map and the four movement directions.

The grid uses screen coordinates: ``x`` grows to the right and ``y`` grows
downwards, so the top-left cell is ``Position(0, 0)``.
"""

from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    """One of the four orthogonal directions a bot can move or shoot in.

    >>> Direction.UP.dx, Direction.UP.dy
    (0, -1)
    >>> Direction.LEFT.opposite
    <Direction.RIGHT: (1, 0)>
    """

    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def dx(self) -> int:
        """Change of the ``x`` coordinate for one step."""
        return self.value[0]

    @property
    def dy(self) -> int:
        """Change of the ``y`` coordinate for one step."""
        return self.value[1]

    @property
    def opposite(self) -> "Direction":
        """The direction pointing the other way."""
        return Direction((-self.dx, -self.dy))


@dataclass(frozen=True)
class Position:
    """An immutable cell coordinate on the grid.

    >>> Position(2, 3).moved(Direction.RIGHT)
    Position(x=3, y=3)
    """

    x: int
    y: int

    def moved(self, direction: Direction) -> "Position":
        """Return the neighbouring position one step in ``direction``.

        Args:
            direction: The direction of the step.

        Returns:
            A new position; this one is left unchanged.
        """
        return Position(self.x + direction.dx, self.y + direction.dy)

    def is_inside(self, size: int) -> bool:
        """Check whether the position lies on a square grid.

        Args:
            size: The width and height of the grid.

        Returns:
            ``True`` if both coordinates are in ``range(size)``.

        >>> Position(0, 19).is_inside(20)
        True
        >>> Position(-1, 0).is_inside(20)
        False
        """
        return 0 <= self.x < size and 0 <= self.y < size

    def rotated(self, size: int) -> "Position":
        """Return the cell this one maps to under a 180° grid rotation.

        Map generation uses this to make the map identical from both
        bases, so neither bot starts with an advantage.

        Args:
            size: The width and height of the grid.

        Returns:
            The rotated position.

        >>> Position(0, 0).rotated(20)
        Position(x=19, y=19)
        """
        return Position(size - 1 - self.x, size - 1 - self.y)


def manhattan(a: Position, b: Position) -> int:
    """Return the number of orthogonal steps between two positions.

    Args:
        a: The first position.
        b: The second position.

    Returns:
        The Manhattan distance, ignoring walls.

    >>> manhattan(Position(0, 0), Position(3, 4))
    7
    """
    return abs(a.x - b.x) + abs(a.y - b.y)
