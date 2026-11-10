"""The public interface for bot authors.

A bot imports everything it needs from this module only::

    from arena.api import Action, BotState, Direction

Besides the game types it offers two helpers: :func:`distance` and the
memoized :func:`shortest_path` (with :func:`next_step` built on it).
"""

from collections import deque

from arena.model.actions import Action
from arena.model.geometry import Direction, Position, manhattan
from arena.model.side import Side
from arena.model.state import (
    BotState,
    Event,
    EventKind,
    GameMap,
    ModeKind,
    OpponentView,
    PlayerState,
    Trap,
)
from arena.rules import Rules
from arena.utilities.decorators import memoize

__all__ = [
    "Action",
    "BotState",
    "Direction",
    "Event",
    "EventKind",
    "GameMap",
    "ModeKind",
    "OpponentView",
    "PlayerState",
    "Position",
    "Rules",
    "Side",
    "Trap",
    "distance",
    "next_step",
    "shortest_path",
]


def distance(a: Position, b: Position) -> int:
    """Return the number of steps between two cells, ignoring walls.

    >>> distance(Position(0, 0), Position(2, 3))
    5
    """
    return manhattan(a, b)


@memoize
def shortest_path(
    game_map: GameMap, start: Position, goal: Position
) -> tuple[Position, ...]:
    """Return the cells of a shortest walk from ``start`` to ``goal``.

    The result starts with the first step and ends with ``goal``. It is
    empty if ``start`` is ``goal`` or the goal cannot be reached. Results
    are cached, because the map never changes during a match.

    Args:
        game_map: The map to walk on.
        start: Where the walk begins (not included in the result).
        goal: Where the walk ends.

    Returns:
        The cells of the walk, in order.
    """
    if start == goal:
        return ()
    came_from: dict[Position, Position] = {start: start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current == goal:
            break
        for direction in Direction:
            cell = current.moved(direction)
            if cell not in came_from and game_map.is_walkable(cell):
                came_from[cell] = current
                queue.append(cell)
    if goal not in came_from:
        return ()
    path = [goal]
    while came_from[path[-1]] != start:
        path.append(came_from[path[-1]])
    return tuple(reversed(path))


def next_step(
    game_map: GameMap, start: Position, goal: Position
) -> Direction | None:
    """Return the direction of the first step towards ``goal``.

    >>> open_map = GameMap(4, frozenset(), {})
    >>> next_step(open_map, Position(0, 0), Position(0, 2))
    <Direction.DOWN: (0, 1)>
    """
    path = shortest_path(game_map, start, goal)
    if not path:
        return None
    first = path[0]
    return next(
        direction for direction in Direction if start.moved(direction) == first
    )
